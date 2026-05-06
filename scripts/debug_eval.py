"""Run one test pair end-to-end and print everything for debugging."""
import os
os.environ["INFERENCE_MODE"] = "sagemaker"

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.services.inference_client import run_inference
from scripts.evaluation.metrics import execute_sql_safe


async def main():
    settings = get_settings()
    print(f"Inference mode: {settings.inference_mode}")  # should print 'sagemaker'

    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    with open("data/synthetic/pg_test.jsonl") as f:
        for line in f:
            d = json.loads(line)
            if d["schema_name"] == "ecommerce":
                pair = d
                break

    print(f"\nQuestion: {pair['question']}")
    print(f"\nReference SQL:\n{pair['sql']}")

    prompt = (
        f"### Schema:\n{pair['schema_ddl']}\n\n"
        f"### Question:\n{pair['question']}\n\n"
        f"### SQL:\n"
    )
    generated_sql, _ = await run_inference(pair["question"], prompt)
    print(f"\nGenerated SQL:\n{generated_sql}")

    print("\n--- Executing reference SQL ---")
    ok, ref_rows, err = await execute_sql_safe(pair["sql"], dsn)
    print(f"Success: {ok}, Error: {err}")
    if ref_rows:
        print(f"Reference rows ({len(ref_rows)}): {ref_rows[:3]}")

    print("\n--- Executing generated SQL ---")
    ok, gen_rows, err = await execute_sql_safe(generated_sql, dsn)
    print(f"Success: {ok}, Error: {err}")
    if gen_rows:
        print(f"Generated rows ({len(gen_rows)}): {gen_rows[:3]}")

    if ref_rows is not None and gen_rows is not None:
        print(f"\nMatch: {ref_rows == gen_rows}")


if __name__ == "__main__":
    asyncio.run(main())