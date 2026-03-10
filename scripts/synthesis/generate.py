"""
PostgreSQL Data Synthesis Pipeline
------------------------------------
Generates execution-validated PostgreSQL question/SQL training pairs
using Groq (llama-3.3-70b-versatile) as the generation LLM.

This is the novel contribution that fills the SQLite-only gap in OmniSQL.

Pipeline:
  1. For each schema: generate N question/SQL pairs via Groq
  2. Validate SQL syntax with sqlparse
  3. Reject SQLite-specific syntax
  4. Execute against real PostgreSQL to confirm correctness
  5. Save validated pairs to JSONL after every batch (crash-safe)

Usage:
    python scripts/synthesis/generate.py --total 2000 --output data/synthetic/pg_train.jsonl

Output format matches OmniSQL training format:
    {schema_name, schema_ddl, question, chain_of_thought, sql, dialect, complexity}
"""

import asyncio
import argparse
import json
import re
import time
import random
import os
from pathlib import Path
from datetime import datetime
from collections import Counter

import asyncpg
import sqlparse
from groq import Groq
import structlog

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import get_settings
from scripts.synthesis.pg_schemas import SCHEMAS

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()
settings = get_settings()

COMPLEXITY_TARGETS = {
    "simple": {
        "weight": 0.25,
        "description": "Basic SELECT with WHERE, ORDER BY, LIMIT",
        "pg_features": ["ILIKE", "BOOLEAN comparisons", "TIMESTAMP comparisons"],
    },
    "moderate": {
        "weight": 0.35,
        "description": "JOINs, GROUP BY, HAVING, basic aggregations",
        "pg_features": ["DATE_TRUNC", "EXTRACT", "COALESCE", "NULLIF"],
    },
    "complex": {
        "weight": 0.25,
        "description": "CTEs, window functions, subqueries",
        "pg_features": [
            "WITH ... AS (CTE)",
            "ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)",
            "LAG/LEAD window functions",
            "RANK() / DENSE_RANK()",
        ],
    },
    "highly_complex": {
        "weight": 0.15,
        "description": "Multiple CTEs, complex window functions, JSONB queries",
        "pg_features": [
            "Multiple CTEs",
            "JSONB operators (->, ->>)",
            "ARRAY_AGG",
            "STRING_AGG",
            "FILTER clause on aggregates",
        ],
    },
}

GENERATION_PROMPT = """You are an expert PostgreSQL database engineer creating training data for a Text-to-SQL model.

Given this PostgreSQL database schema:

{schema_ddl}

Sample values in the database:
{sample_values}

Generate exactly {batch_size} diverse question/SQL pairs at {complexity} complexity level.

Complexity guidelines for {complexity}:
- Description: {complexity_description}
- Must use at least one of these PostgreSQL-specific features: {pg_features}

Requirements:
1. Questions must be natural, varied phrasing (formal, casual, imperative, vague)
2. SQL must be valid PostgreSQL syntax - NOT SQLite syntax
3. Use PostgreSQL functions: DATE_TRUNC, EXTRACT, ILIKE, COALESCE, window functions, CTEs as appropriate
4. Never use SQLite-specific syntax like strftime(), datetime('now'), etc.
5. Each question must be answerable from the schema alone
6. Include chain-of-thought reasoning before the SQL

Output ONLY a JSON array, no other text before or after:
[
  {{
    "question": "natural language question here",
    "chain_of_thought": "Step 1: ... Step 2: ... Step 3: ...",
    "sql": "SELECT ... FROM ... WHERE ...;"
  }}
]"""


def init_groq(api_key: str) -> Groq:
    return Groq(api_key=api_key)


def call_groq(client: Groq, prompt: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def parse_response(response_text: str) -> list[dict]:
    text = response_text.strip()
    if "```json" in text:
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    elif "```" in text:
        text = re.sub(r"```\w*\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON array found in response")
    return json.loads(text[start:end])


def is_valid_syntax(sql: str) -> bool:
    try:
        parsed = sqlparse.parse(sql.rstrip(";"))
        return bool(parsed and parsed[0].tokens)
    except Exception:
        return False


def is_postgresql_sql(sql: str) -> bool:
    sqlite_patterns = [
        r"strftime\s*\(",
        r"datetime\s*\(\s*['\"]now",
        r"date\s*\(\s*['\"]now",
        r"julianday\s*\(",
        r"typeof\s*\(",
    ]
    sql_lower = sql.lower()
    for pattern in sqlite_patterns:
        if re.search(pattern, sql_lower):
            return False
    return True


async def execute_validate(sql: str, dsn: str) -> tuple[bool, str | None]:
    try:
        conn = await asyncpg.connect(dsn)
        try:
            async with conn.transaction():
                test_sql = sql.rstrip(";")
                if test_sql.strip().upper().startswith("SELECT") and "LIMIT" not in test_sql.upper():
                    test_sql = f"{test_sql} LIMIT 1"
                await conn.fetch(test_sql)
                raise Exception("ROLLBACK")
        except Exception as e:
            if "ROLLBACK" in str(e):
                return True, None
            return False, str(e)
        finally:
            await conn.close()
    except Exception as e:
        return False, str(e)


def save_pairs(output_path: str, all_pairs: list[dict]):
    """Save all pairs to JSONL atomically."""
    with open(output_path, "w") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair) + "\n")


async def setup_schema_tables(schema: dict, dsn: str):
    conn = await asyncpg.connect(dsn)
    try:
        statements = [s.strip() for s in schema["ddl"].split(";") if s.strip()]
        for stmt in statements:
            try:
                await conn.execute(stmt)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    log.debug("Schema setup warning", error=str(e)[:80])
        log.info("Schema tables ready", schema=schema["name"])
    finally:
        await conn.close()


async def generate_for_schema(
    client: Groq,
    schema: dict,
    target_count: int,
    dsn: str,
    batch_size: int = 10,
    output_path: str = None,
    all_existing_pairs: list = None,
    already_have: int = 0,
) -> list[dict]:
    """
    Generate execution-validated pairs for a single schema.

    Saves after every batch — rate limit interruptions lose at most
    one batch of 10 pairs, not an entire schema run.

    already_have: pairs already saved for this schema on disk,
                  so we only generate the remaining needed.
    """
    all_existing_pairs = all_existing_pairs or []
    validated_pairs = []
    attempts = 0

    effective_target = target_count - already_have
    if effective_target <= 0:
        log.info("Schema already complete, skipping", schema=schema["name"])
        return []

    max_attempts = effective_target * 4

    complexities = []
    for complexity, config in COMPLEXITY_TARGETS.items():
        count = int(effective_target * config["weight"])
        complexities.extend([complexity] * count)
    while len(complexities) < effective_target:
        complexities.append("moderate")
    random.shuffle(complexities)

    complexity_idx = 0

    log.info(
        "Generating pairs for schema",
        schema=schema["name"],
        target=effective_target,
        already_have=already_have,
    )

    sample_values_str = "\n".join(
        f"  - {col}: {values}"
        for col, values in schema.get("sample_values", {}).items()
    )

    while len(validated_pairs) < effective_target and attempts < max_attempts:
        remaining = effective_target - len(validated_pairs)
        current_batch = min(batch_size, remaining + 5)
        complexity = complexities[complexity_idx % len(complexities)]
        complexity_idx += 1
        attempts += current_batch

        complexity_config = COMPLEXITY_TARGETS[complexity]

        prompt = GENERATION_PROMPT.format(
            schema_ddl=schema["ddl"].strip(),
            sample_values=sample_values_str or "  No sample values provided",
            batch_size=current_batch,
            complexity=complexity,
            complexity_description=complexity_config["description"],
            pg_features=", ".join(complexity_config["pg_features"]),
        )

        try:
            raw = call_groq(client, prompt)
            pairs = parse_response(raw)

            for pair in pairs:
                if len(validated_pairs) >= effective_target:
                    break

                sql = pair.get("sql", "").strip()
                question = pair.get("question", "").strip()
                cot = pair.get("chain_of_thought", "").strip()

                if not sql or not question:
                    continue
                if not is_valid_syntax(sql):
                    log.debug("Syntax invalid, skipping", sql=sql[:60])
                    continue
                if not is_postgresql_sql(sql):
                    log.debug("SQLite syntax detected, skipping", sql=sql[:60])
                    continue

                success, error = await execute_validate(sql, dsn)
                if not success:
                    log.debug("Execution failed, skipping", error=str(error)[:80])
                    continue

                validated_pairs.append({
                    "schema_name": schema["name"],
                    "schema_ddl": schema["ddl"].strip(),
                    "question": question,
                    "chain_of_thought": cot,
                    "sql": sql,
                    "dialect": "postgresql",
                    "complexity": complexity,
                    "generated_at": datetime.now().isoformat(),
                })

            log.info(
                "Batch complete",
                schema=schema["name"],
                validated=len(validated_pairs),
                target=effective_target,
                attempts=attempts,
            )

            # ── Save after every batch ────────────────────────────────────
            # Key fix: saves mid-schema so rate limit interruptions
            # don't lose progress. Tomorrow's resume tops up from here.
            if output_path:
                save_pairs(output_path, all_existing_pairs + validated_pairs)

            # Groq free tier: 30 RPM — stay safe at ~10 RPM
            time.sleep(6)

        except Exception as e:
            log.warning("Batch failed", error=str(e)[:150])
            time.sleep(10)
            continue

    log.info(
        "Schema complete",
        schema=schema["name"],
        validated=len(validated_pairs),
        target=effective_target,
        success_rate=f"{len(validated_pairs)/max(attempts,1)*100:.1f}%",
    )

    return validated_pairs


async def run_synthesis(
    api_key: str,
    total_pairs: int,
    output_path: str,
    resume: bool = True,
):
    """Main synthesis runner with crash-safe incremental saving."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    existing_pairs = []
    if resume and output_file.exists():
        with open(output_file) as f:
            existing_pairs = [json.loads(line) for line in f if line.strip()]
        log.info(f"Resuming: found {len(existing_pairs)} existing pairs")

    existing_schema_counts = Counter(p["schema_name"] for p in existing_pairs)
    pairs_per_schema_target = total_pairs // len(SCHEMAS)

    fully_done = {
        name for name, count in existing_schema_counts.items()
        if count >= pairs_per_schema_target
    }

    partial = {
        name: count for name, count in existing_schema_counts.items()
        if 0 < count < pairs_per_schema_target
    }

    log.info(
        "Schema status",
        fully_done=fully_done,
        partial=partial,
        counts=dict(existing_schema_counts),
    )

    client = init_groq(api_key)
    log.info("Groq initialized", model="llama-3.3-70b-versatile")

    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    schemas_to_run = [s for s in SCHEMAS if s["name"] not in fully_done]
    if not schemas_to_run:
        log.info("All schemas already generated!")
        return

    log.info(
        "Starting synthesis",
        total_target=total_pairs,
        existing=len(existing_pairs),
        schemas_to_run=[s["name"] for s in schemas_to_run],
    )

    all_pairs = existing_pairs.copy()

    for schema in schemas_to_run:
        already_have = existing_schema_counts.get(schema["name"], 0)

        await setup_schema_tables(schema, dsn)
        new_pairs = await generate_for_schema(
            client=client,
            schema=schema,
            target_count=pairs_per_schema_target,
            dsn=dsn,
            output_path=str(output_file),
            all_existing_pairs=all_pairs.copy(),
            already_have=already_have,
        )

        all_pairs.extend(new_pairs)
        save_pairs(str(output_file), all_pairs)
        log.info("Schema saved", schema=schema["name"], total_saved=len(all_pairs))

    complexity_counts = Counter(p["complexity"] for p in all_pairs)
    schema_counts = Counter(p["schema_name"] for p in all_pairs)

    log.info("=" * 50)
    log.info(f"✅ Synthesis complete! Total pairs: {len(all_pairs)}")
    log.info(f"   Output: {output_file}")
    log.info(f"   Complexity: {dict(complexity_counts)}")
    log.info(f"   By schema: {dict(schema_counts)}")

    return all_pairs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate PostgreSQL Text-to-SQL training data")
    parser.add_argument("--total", type=int, default=2000, help="Total pairs to generate")
    parser.add_argument("--output", default="data/synthetic/pg_train.jsonl", help="Output JSONL path")
    parser.add_argument("--api-key", help="Groq API key (or set GROQ_API_KEY in .env)")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh")
    args = parser.parse_args()

    api_key = args.api_key
    if not api_key:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print("❌ No Groq API key found. Set GROQ_API_KEY in .env or pass --api-key")
        sys.exit(1)

    asyncio.run(run_synthesis(
        api_key=api_key,
        total_pairs=args.total,
        output_path=args.output,
        resume=not args.no_resume,
    ))