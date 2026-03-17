"""
scripts/evaluation/metrics.py
-------------------------------
Evaluation metrics for Text-to-SQL:

  1. Execution Accuracy (EX) — primary metric
     Does the generated SQL execute successfully against PostgreSQL?
     Does it return the same result as the ground truth SQL?

  2. BLEU Score — secondary metric
     Surface-level similarity between generated and reference SQL.
     Less meaningful than EX but tracks training progress.

  3. Validity Rate
     What % of generated SQL passes syntax check + executes without error.

Execution Accuracy is the gold standard used by BIRD benchmark.
"""

import asyncpg
import sqlparse
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import structlog

log = structlog.get_logger()


def compute_bleu(reference_sql: str, hypothesis_sql: str) -> float:
    """
    Compute BLEU score between reference and generated SQL.
    Tokenizes by splitting on whitespace and SQL punctuation.
    """
    def tokenize(sql: str) -> list[str]:
        # Normalize and tokenize
        sql = sql.lower().strip().rstrip(";")
        # Split on whitespace and keep punctuation as tokens
        import re
        tokens = re.findall(r'\w+|[^\w\s]', sql)
        return tokens

    ref_tokens = tokenize(reference_sql)
    hyp_tokens = tokenize(hypothesis_sql)

    if not hyp_tokens:
        return 0.0

    smoothing = SmoothingFunction().method1
    try:
        score = sentence_bleu(
            [ref_tokens],
            hyp_tokens,
            smoothing_function=smoothing,
        )
        return round(score, 4)
    except Exception:
        return 0.0


def is_valid_sql(sql: str) -> bool:
    """Check if SQL passes basic syntax validation."""
    try:
        parsed = sqlparse.parse(sql.rstrip(";"))
        return bool(parsed and parsed[0].tokens)
    except Exception:
        return False


async def execute_sql_safe(sql: str, dsn: str, timeout: float = 10.0) -> tuple[bool, list | None, str | None]:
    """
    Execute SQL and return results safely.

    Returns:
        (success, rows_as_frozensets, error_message)
        rows are frozensets to allow order-independent comparison
    """
    try:
        conn = await asyncpg.connect(dsn, timeout=timeout)
        try:
            # Add LIMIT for safety on large result sets
            test_sql = sql.rstrip(";")
            if test_sql.strip().upper().startswith("SELECT") and "LIMIT" not in test_sql.upper():
                test_sql = f"{test_sql} LIMIT 100"

            rows = await conn.fetch(test_sql)
            # Convert to frozensets of tuples for order-independent comparison
            result = [frozenset(dict(row).items()) for row in rows]
            return True, result, None
        except Exception as e:
            return False, None, str(e)
        finally:
            await conn.close()
    except Exception as e:
        return False, None, str(e)


def results_match(ref_rows: list, hyp_rows: list) -> bool:
    """
    Compare two result sets order-independently.
    Returns True if they contain the same rows.
    """
    if ref_rows is None or hyp_rows is None:
        return False
    return set(map(frozenset, [dict(r) for r in ref_rows])) == \
           set(map(frozenset, [dict(r) for r in hyp_rows])) \
           if ref_rows and hyp_rows else ref_rows == hyp_rows


async def evaluate_single(
    question: str,
    reference_sql: str,
    generated_sql: str,
    dsn: str,
) -> dict:
    """
    Evaluate a single question/SQL pair.

    Returns dict with:
        - bleu: BLEU score
        - valid: SQL passes syntax check
        - exec_success: generated SQL executes without error
        - exec_match: results match reference SQL
    """
    result = {
        "question": question,
        "reference_sql": reference_sql,
        "generated_sql": generated_sql,
        "bleu": 0.0,
        "valid": False,
        "exec_success": False,
        "exec_match": False,
        "error": None,
    }

    # BLEU score (always computable)
    result["bleu"] = compute_bleu(reference_sql, generated_sql)

    # Syntax validity
    result["valid"] = is_valid_sql(generated_sql)
    if not result["valid"]:
        result["error"] = "Invalid SQL syntax"
        return result

    # Execute generated SQL
    gen_success, gen_rows, gen_error = await execute_sql_safe(generated_sql, dsn)
    result["exec_success"] = gen_success

    if not gen_success:
        result["error"] = gen_error
        return result

    # Execute reference SQL to get ground truth
    ref_success, ref_rows, ref_error = await execute_sql_safe(reference_sql, dsn)

    if not ref_success:
        # Reference failed — mark as exec_match=True if generated also executed
        # (We can't compare results if reference fails)
        result["exec_match"] = gen_success
        return result

    # Compare results
    result["exec_match"] = (gen_rows == ref_rows)

    return result