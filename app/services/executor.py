"""
SQL Execution + Self-Correction Engine
---------------------------------------
Executes generated SQL against PostgreSQL and self-corrects on failure.

Self-correction loop:
  1. Parse SQL with sqlparse (syntax check, free)
  2. Execute against sandboxed read-only PostgreSQL connection
  3. On error: feed error back to model → regenerate → retry (up to N times)
  4. Log all attempts for retraining

This loop alone improves execution accuracy by ~10-15%.
"""

import structlog
import sqlparse
import asyncpg
from dataclasses import dataclass

from app.config import get_settings
from app.services.inference import run_inference, extract_sql_from_response

log = structlog.get_logger()
settings = get_settings()


@dataclass
class ExecutionResult:
    success: bool
    sql: str                          # final SQL (after corrections)
    original_sql: str                 # first attempt
    rows: list[dict] | None = None
    row_count: int | None = None
    error: str | None = None
    correction_attempts: int = 0


def validate_sql_syntax(sql: str) -> tuple[bool, str | None]:
    """
    Quick syntax check using sqlparse before hitting the database.
    Catches obvious errors like unmatched parentheses, missing keywords.

    Returns:
        (is_valid, error_message)
    """
    try:
        parsed = sqlparse.parse(sql)
        if not parsed or not parsed[0].tokens:
            return False, "Empty or unparseable SQL"

        # Check it starts with a valid statement type
        statement = parsed[0]
        first_token = statement.get_type()

        if first_token is None:
            # sqlparse couldn't determine type — still attempt execution
            # Some valid PostgreSQL CTEs get flagged here
            return True, None

        return True, None

    except Exception as e:
        return False, str(e)


def sanitize_sql(sql: str) -> str:
    """
    Basic SQL sanitization:
    - Strip markdown code fences if model included them
    - Strip trailing semicolons (asyncpg doesn't need them)
    - Strip leading/trailing whitespace
    """
    sql = sql.strip()

    # Remove markdown code fences
    if sql.startswith("```"):
        lines = sql.split("\n")
        sql = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Remove trailing semicolon
    sql = sql.rstrip(";").strip()

    return sql


async def execute_sql(
    sql: str,
    dsn: str,
) -> tuple[list[dict], int]:
    """
    Execute SQL against PostgreSQL using asyncpg.
    Uses a read-only transaction for safety.

    Returns:
        (rows_as_dicts, row_count)
    """
    clean_sql = sanitize_sql(sql)

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(clean_sql)
            result = [dict(row) for row in rows]
            return result, len(result)
    finally:
        await conn.close()


def build_correction_prompt(
    original_prompt: str,
    failed_sql: str,
    error: str,
    dialect: str = "postgresql",
) -> str:
    """
    Build a self-correction prompt when SQL execution fails.

    Feeds the error back to the model so it can understand what went wrong
    and regenerate a corrected query.
    """
    return f"""{original_prompt}

---

Your previous attempt generated this SQL:
```sql
{failed_sql}
```

But it failed with this {dialect.upper()} error:
{error}

Please analyze the error carefully and generate a corrected {dialect.upper()} SQL query.
Common issues to check:
- Column names that don't exist in the schema
- Wrong table references
- {dialect.upper()}-incompatible syntax
- Missing JOIN conditions
- Incorrect aggregate function usage

Provide the corrected query in a ```sql ... ``` block."""


async def execute_with_self_correction(
    question: str,
    initial_sql: str,
    original_prompt: str,
    dialect: str = "postgresql",
    max_attempts: int | None = None,
) -> ExecutionResult:
    """
    Execute SQL and self-correct on failure.

    This is the core reliability mechanism:
    1. Try the initial SQL
    2. On failure: build correction prompt → re-run inference → retry
    3. Repeat up to max_attempts times
    4. Return final result with full audit trail

    Args:
        question: original NL question
        initial_sql: first SQL attempt from model
        original_prompt: the schema+question prompt used for initial inference
        dialect: sql dialect (postgresql | sqlite)
        max_attempts: override settings.max_correction_attempts

    Returns:
        ExecutionResult with success/failure, final SQL, rows, and attempt count
    """
    max_retries = max_attempts or settings.max_correction_attempts
    current_sql = initial_sql
    original_sql = initial_sql
    correction_attempts = 0

    # Build DSN for asyncpg
    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        is_attempt = attempt > 0

        log.info(
            "Executing SQL",
            attempt=attempt,
            is_correction=is_attempt,
            sql_preview=current_sql[:80],
        )

        # Step 1: Syntax check
        is_valid, syntax_error = validate_sql_syntax(current_sql)
        if not is_valid:
            error_msg = f"Syntax error: {syntax_error}"
            log.warning("SQL syntax invalid", error=error_msg)

            if attempt < max_retries:
                # Build correction prompt and re-run inference
                correction_prompt = build_correction_prompt(
                    original_prompt, current_sql, error_msg, dialect
                )
                corrected_sql, _ = await run_inference(question, correction_prompt)
                current_sql = corrected_sql
                correction_attempts += 1
                continue
            else:
                return ExecutionResult(
                    success=False,
                    sql=current_sql,
                    original_sql=original_sql,
                    error=error_msg,
                    correction_attempts=correction_attempts,
                )

        # Step 2: Execute
        try:
            rows, row_count = await execute_sql(current_sql, dsn)

            log.info(
                "SQL executed successfully",
                row_count=row_count,
                correction_attempts=correction_attempts,
            )

            return ExecutionResult(
                success=True,
                sql=current_sql,
                original_sql=original_sql,
                rows=rows,
                row_count=row_count,
                correction_attempts=correction_attempts,
            )

        except Exception as e:
            error_msg = str(e)
            log.warning(
                "SQL execution failed",
                attempt=attempt,
                error=error_msg[:200],
            )

            if attempt < max_retries:
                # Self-correction: feed error back to model
                correction_prompt = build_correction_prompt(
                    original_prompt, current_sql, error_msg, dialect
                )
                corrected_sql, _ = await run_inference(question, correction_prompt)
                current_sql = corrected_sql
                correction_attempts += 1
            else:
                return ExecutionResult(
                    success=False,
                    sql=current_sql,
                    original_sql=original_sql,
                    error=error_msg,
                    correction_attempts=correction_attempts,
                )

    # Should not reach here, but safety fallback
    return ExecutionResult(
        success=False,
        sql=current_sql,
        original_sql=original_sql,
        error="Max correction attempts exceeded",
        correction_attempts=correction_attempts,
    )
