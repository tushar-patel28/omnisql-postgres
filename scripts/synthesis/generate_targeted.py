"""
scripts/synthesis/generate_targeted.py
----------------------------------------
Targeted training-pair generator that reuses the existing infrastructure
(setup_schema_tables, validation, save-after-batch) but biases generation
toward the specific failure patterns identified in eval v2.

Failure patterns we target:
  - LIST_WITH_DETAIL    : question asks for per-row detail; model collapses to scalar
  - TIME_SERIES         : question implies a per-month/per-week breakdown
  - WINDOW_FUNCTIONS    : RANK / ROW_NUMBER / LAG / LEAD usage
  - MULTI_JOIN_FILTER   : 3+ table joins with non-trivial WHERE clauses

Each pattern has its own prompt template. We generate `--per-schema-per-pattern`
pairs of each pattern for each of the 5 schemas. With the default 30, that's
30 * 5 * 4 = 600 new pairs.

Usage:
    python scripts/synthesis/generate_targeted.py \\
        --output data/synthetic/pg_finetune_v2_targeted.jsonl \\
        --per-schema-per-pattern 30
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import structlog

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import get_settings
from scripts.synthesis.pg_schemas import SCHEMAS
from scripts.synthesis.generate import (
    parse_response,
    is_valid_syntax,
    is_postgresql_sql,
    execute_validate,
    setup_schema_tables,
    save_pairs,
)

from openai import OpenAI


def init_deepseek(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def call_deepseek(client: OpenAI, prompt: str) -> str:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=4096,
    )
    return response.choices[0].message.content

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()
settings = get_settings()


# ── Pattern definitions ──────────────────────────────────────────────────────

PATTERNS = {
    "LIST_WITH_DETAIL": {
        "complexity": "moderate",
        "description": (
            "List queries that return per-row detail without collapsing into a single scalar. "
            "The question asks for a *list* or *each* item, NOT an aggregate."
        ),
        "must_use": [
            "Multiple selected columns showing per-row detail",
            "JOIN across 2-3 tables",
            "WHERE filter (no GROUP BY, or GROUP BY only when aggregating sub-fields)",
        ],
        "examples_of_questions": [
            "List all orders with the customer name and total amount, including ones placed in the last 30 days.",
            "Show me each employee's name, department, and current salary.",
            "Get every appointment with the patient's name and the provider's specialty.",
        ],
        "anti_patterns": [
            "Do not produce a single-row scalar like SELECT COUNT(*) FROM ...",
            "Do not aggregate when the question says 'list', 'show me', 'get all', 'each'",
        ],
    },

    "TIME_SERIES": {
        "complexity": "complex",
        "description": (
            "Time-series breakdown queries. The output must have one row per "
            "time bucket (per month, per week, per quarter, per day)."
        ),
        "must_use": [
            "DATE_TRUNC('month' or 'week' or 'quarter', <timestamp>) in SELECT and GROUP BY",
            "ORDER BY the time bucket ascending",
            "An aggregate per bucket (COUNT, SUM, AVG)",
        ],
        "examples_of_questions": [
            "What is the monthly revenue from all subscriptions over the last year?",
            "How many orders were placed each week in 2024?",
            "Show the average appointment count per quarter, broken down by quarter.",
        ],
        "anti_patterns": [
            "Do not return a single total — every row must represent one time bucket.",
            "Do not omit the time bucket column from the SELECT list.",
        ],
    },

    "WINDOW_FUNCTIONS": {
        "complexity": "complex",
        "description": (
            "Queries that use window functions (RANK, ROW_NUMBER, LAG, LEAD, "
            "running totals). Window functions preserve row count."
        ),
        "must_use": [
            "OVER (PARTITION BY ... ORDER BY ...) clause",
            "One of: RANK(), DENSE_RANK(), ROW_NUMBER(), LAG(), LEAD(), SUM() OVER",
            "The window function appears in SELECT, not in WHERE",
        ],
        "examples_of_questions": [
            "Rank each customer by total spent, partitioned by their tier.",
            "For each employee, show their salary and their rank within their department.",
            "Show each transaction along with the running total for that account, in chronological order.",
        ],
        "anti_patterns": [
            "Do not put window functions inside WHERE — wrap with a CTE or subquery first.",
            "Do not collapse the result with GROUP BY — window functions are per-row.",
        ],
    },

    "MULTI_JOIN_FILTER": {
        "complexity": "highly_complex",
        "description": (
            "Queries that join 3+ tables with non-trivial WHERE filters that "
            "test the model's ability to keep track of which table each "
            "column belongs to."
        ),
        "must_use": [
            "JOIN across at least 3 tables",
            "WHERE clause with conditions on multiple joined tables",
            "Aliased table names (e.g. e, d, pr for employees/departments/performance_reviews)",
        ],
        "examples_of_questions": [
            "Find patients who saw a cardiology specialist in the last 90 days and were diagnosed with hypertension.",
            "List employees in the Engineering department whose most recent performance review rating was above 4.0.",
            "Show organizations whose owners triggered more than 100 events last month.",
        ],
        "anti_patterns": [
            "Do not over-CTE — straightforward JOIN+WHERE is fine.",
            "Do not invent columns the schema doesn't have.",
        ],
    },
}


PROMPT_TEMPLATE = """You are an expert PostgreSQL database engineer creating training data for a Text-to-SQL model.

Given this PostgreSQL database schema:

{schema_ddl}

Sample values in the database:
{sample_values}

Generate exactly {batch_size} diverse question/SQL pairs of pattern: {pattern_name}

Pattern description: {pattern_description}

Required SQL features for this pattern:
{must_use}

Strictly avoid these mistakes:
{anti_patterns}

Reference questions in this style (for tone, NOT to copy):
{example_questions}

General requirements:
1. Use natural, varied phrasing — formal, casual, imperative, vague.
2. SQL must be valid PostgreSQL — NOT SQLite. Never use strftime, julianday, datetime('now').
3. Use PostgreSQL idioms: DATE_TRUNC, EXTRACT, ILIKE, COALESCE, INTERVAL.
4. Each question must be answerable from the schema alone.
5. Include a brief chain-of-thought reasoning before the SQL.

Output ONLY a JSON array, no other text:
[
  {{
    "question": "natural language question here",
    "chain_of_thought": "Step 1: ... Step 2: ... Step 3: ...",
    "sql": "SELECT ... FROM ... WHERE ...;"
  }}
]"""


def build_prompt(schema: dict, pattern_name: str, batch_size: int) -> str:
    pattern = PATTERNS[pattern_name]
    sample_values_str = "\n".join(
        f"  - {col}: {values}"
        for col, values in schema.get("sample_values", {}).items()
    ) or "  (no sample values)"

    return PROMPT_TEMPLATE.format(
        schema_ddl=schema["ddl"].strip(),
        sample_values=sample_values_str,
        batch_size=batch_size,
        pattern_name=pattern_name,
        pattern_description=pattern["description"],
        must_use="\n".join(f"  - {x}" for x in pattern["must_use"]),
        anti_patterns="\n".join(f"  - {x}" for x in pattern["anti_patterns"]),
        example_questions="\n".join(f"  - {x}" for x in pattern["examples_of_questions"]),
    )


# ── Pattern-specific validators ──────────────────────────────────────────────

def passes_pattern_check(sql: str, pattern_name: str) -> bool:
    """Light heuristic check that the SQL actually matches the pattern."""
    s = sql.lower()

    if pattern_name == "TIME_SERIES":
        # Must use DATE_TRUNC and GROUP BY
        return "date_trunc" in s and "group by" in s

    if pattern_name == "WINDOW_FUNCTIONS":
        return " over " in s and ("partition by" in s or "order by" in s)

    if pattern_name == "MULTI_JOIN_FILTER":
        # At least 2 JOIN keywords (so 3 tables)
        return s.count(" join ") >= 2 and " where " in s

    if pattern_name == "LIST_WITH_DETAIL":
        # Must NOT be a single scalar — should not be just "select count(*)..."
        if re.search(r"^\s*select\s+count\s*\(\s*\*\s*\)\s+from", s):
            return False
        if re.search(r"^\s*select\s+(avg|sum|min|max)\s*\(", s) and "group by" not in s:
            return False
        # Should have some kind of join or multi-column select
        return " join " in s or s.count(",") >= 1

    return True


# ── Main generation ──────────────────────────────────────────────────────────

async def generate_pattern_for_schema(
    client,
    schema: dict,
    pattern_name: str,
    target_count: int,
    dsn: str,
    output_path: str,
    all_existing_pairs: list,
    batch_size: int = 8,
) -> list[dict]:
    """Generate `target_count` validated pairs of `pattern_name` for `schema`."""
    pattern_cfg = PATTERNS[pattern_name]
    complexity = pattern_cfg["complexity"]
    validated = []
    attempts = 0
    max_attempts = target_count * 5  # generous budget

    log.info(
        "Generating pattern",
        schema=schema["name"],
        pattern=pattern_name,
        target=target_count,
    )

    while len(validated) < target_count and attempts < max_attempts:
        remaining = target_count - len(validated)
        current_batch = min(batch_size, remaining + 4)
        attempts += current_batch

        prompt = build_prompt(schema, pattern_name, current_batch)

        try:
            raw = call_deepseek(client, prompt)
            pairs = parse_response(raw)

            for pair in pairs:
                if len(validated) >= target_count:
                    break

                sql = (pair.get("sql") or "").strip()
                question = (pair.get("question") or "").strip()
                cot = (pair.get("chain_of_thought") or "").strip()

                if not sql or not question:
                    continue
                if not is_valid_syntax(sql):
                    continue
                if not is_postgresql_sql(sql):
                    continue
                if not passes_pattern_check(sql, pattern_name):
                    log.debug("Pattern check failed", pattern=pattern_name, sql=sql[:80])
                    continue

                ok, err = await execute_validate(sql, dsn)
                if not ok:
                    continue

                validated.append({
                    "schema_name":   schema["name"],
                    "schema_ddl":    schema["ddl"].strip(),
                    "question":      question,
                    "chain_of_thought": cot,
                    "sql":           sql,
                    "dialect":       "postgresql",
                    "complexity":    complexity,
                    "pattern":       pattern_name,
                    "generated_at":  datetime.now().isoformat(),
                })

            log.info(
                "Batch",
                schema=schema["name"],
                pattern=pattern_name,
                done=len(validated),
                target=target_count,
                attempts=attempts,
            )

            # Save after every batch
            save_pairs(output_path, all_existing_pairs + validated)

            # Groq RPM limit: stay safe
            time.sleep(6)

        except Exception as e:
            log.warning("Batch failed", error=str(e)[:150])
            time.sleep(10)
            continue

    log.info(
        "Pattern complete",
        schema=schema["name"],
        pattern=pattern_name,
        validated=len(validated),
        success_rate=f"{len(validated)/max(attempts,1)*100:.1f}%",
    )
    return validated


async def run(
    api_key: str,
    output_path: str,
    per_schema_per_pattern: int,
    resume: bool,
):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if resume and out.exists():
        with open(out) as f:
            existing = [json.loads(line) for line in f if line.strip()]
        log.info(f"Resuming: {len(existing)} existing pairs")

    # Build (schema, pattern) -> count_so_far map
    have = Counter(
        (p["schema_name"], p.get("pattern", "UNKNOWN")) for p in existing
    )

    client = init_deepseek(api_key)
    log.info("DeepSeek initialized", model="deepseek-chat")

    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    all_pairs = existing.copy()

    for schema in SCHEMAS:
        await setup_schema_tables(schema, dsn)
        for pattern_name in PATTERNS:
            already = have.get((schema["name"], pattern_name), 0)
            need = per_schema_per_pattern - already
            if need <= 0:
                log.info(
                    "Pattern already complete, skipping",
                    schema=schema["name"],
                    pattern=pattern_name,
                    count=already,
                )
                continue

            new_pairs = await generate_pattern_for_schema(
                client=client,
                schema=schema,
                pattern_name=pattern_name,
                target_count=need,
                dsn=dsn,
                output_path=str(out),
                all_existing_pairs=all_pairs.copy(),
            )
            all_pairs.extend(new_pairs)
            save_pairs(str(out), all_pairs)

    # Summary
    by_pattern = Counter(p.get("pattern", "UNKNOWN") for p in all_pairs)
    by_schema = Counter(p["schema_name"] for p in all_pairs)
    by_complexity = Counter(p.get("complexity", "?") for p in all_pairs)

    log.info("=" * 60)
    log.info(f"✅ Targeted synthesis complete: {len(all_pairs)} total pairs")
    log.info(f"   Output: {out}")
    log.info(f"   By pattern:    {dict(by_pattern)}")
    log.info(f"   By schema:     {dict(by_schema)}")
    log.info(f"   By complexity: {dict(by_complexity)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="data/synthetic/pg_finetune_v2_targeted.jsonl",
    )
    parser.add_argument(
        "--per-schema-per-pattern",
        type=int,
        default=30,
        help="Pairs per (schema, pattern). Default 30 → 5×4×30 = 600 total.",
    )
    parser.add_argument("--api-key")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    api_key = args.api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ No DeepSeek API key found. Set DEEPSEEK_API_KEY in .env or pass --api-key")
        sys.exit(1)

    asyncio.run(run(
        api_key=api_key,
        output_path=args.output,
        per_schema_per_pattern=args.per_schema_per_pattern,
        resume=not args.no_resume,
    ))