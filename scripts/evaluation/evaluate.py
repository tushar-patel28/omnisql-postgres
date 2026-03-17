"""
scripts/evaluation/evaluate.py
--------------------------------
Evaluates OmniSQL-7B (baseline or fine-tuned) against the PostgreSQL test set.

Metrics tracked:
  - Execution Accuracy (EX): % of queries that execute AND match reference results
  - Validity Rate: % of queries that execute without error
  - BLEU Score: average surface similarity to reference SQL
  - Per-schema and per-complexity breakdowns

All results logged to Weights & Biases for experiment tracking.

Usage:
    # Baseline evaluation (before fine-tuning)
    python scripts/evaluation/evaluate.py --mode local --run-name "omnisql-7b-baseline"

    # Post fine-tuning evaluation
    python scripts/evaluation/evaluate.py --mode local --model-path path/to/finetuned --run-name "omnisql-pg-v1"

    # Mock mode (fast, no GPU needed, for testing the pipeline)
    python scripts/evaluation/evaluate.py --mode mock --run-name "mock-test"
"""

import asyncio
import argparse
import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import wandb
import structlog

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import get_settings
from app.services.rag import build_prompt, retrieve_relevant_tables
from app.services.inference import run_inference, extract_sql_from_response
from scripts.evaluation.metrics import evaluate_single, compute_bleu, is_valid_sql

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()
settings = get_settings()

TEST_PATH = "data/synthetic/pg_test.jsonl"


def load_test_set(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def build_prompt_from_pair(pair: dict) -> str:
    """Build OmniSQL prompt directly from a test pair's DDL."""
    return f"""Task Overview:
You are a data science expert. Below, you are provided with a database schema and a natural language question. Your task is to understand the schema and generate a valid SQL query to answer the question.

Database Engine:
POSTGRESQL

Database Schema:
{pair['schema_ddl']}

Question:
{pair['question']}

Instructions:
- Generate POSTGRESQL-compatible SQL only.
- Use PostgreSQL-specific functions where appropriate (DATE_TRUNC, ILIKE, window functions, CTEs).
- Before generating the final SQL query, think through the steps.

Output Format:
Enclose the generated SQL query in a code block:
```sql
-- Your SQL query
```

Take a deep breath and think step by step."""


async def run_evaluation(
    mode: str,
    run_name: str,
    model_path: str,
    test_path: str,
    limit: int | None,
):
    """
    Main evaluation loop.

    For each test pair:
    1. Build prompt from schema DDL + question
    2. Run inference (mock/local/sagemaker)
    3. Extract SQL from response
    4. Execute against PostgreSQL + compare to reference
    5. Log all metrics to W&B
    """
    test_pairs = load_test_set(test_path)
    if limit:
        test_pairs = test_pairs[:limit]

    log.info(
        "Starting evaluation",
        run_name=run_name,
        mode=mode,
        test_pairs=len(test_pairs),
    )

    # Override inference mode
    os.environ["INFERENCE_MODE"] = mode

    # Initialize W&B
    wandb.init(
        project="omnisql-postgres",
        name=run_name,
        config={
            "model": model_path or "seeklhy/OmniSQL-7B",
            "mode": mode,
            "test_size": len(test_pairs),
            "test_path": test_path,
            "dialect": "postgresql",
            "evaluated_at": datetime.now().isoformat(),
        },
    )

    # Build DSN
    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    results = []
    per_schema = defaultdict(list)
    per_complexity = defaultdict(list)

    for i, pair in enumerate(test_pairs):
        log.info(
            "Evaluating",
            progress=f"{i+1}/{len(test_pairs)}",
            schema=pair["schema_name"],
            complexity=pair["complexity"],
        )

        # Build prompt and run inference
        prompt = build_prompt_from_pair(pair)

        try:
            generated_sql, explanation = await run_inference(pair["question"], prompt)
        except Exception as e:
            log.warning("Inference failed", error=str(e)[:100])
            generated_sql = ""
            explanation = ""

        # Evaluate
        eval_result = await evaluate_single(
            question=pair["question"],
            reference_sql=pair["sql"],
            generated_sql=generated_sql,
            dsn=dsn,
        )

        eval_result["schema_name"] = pair["schema_name"]
        eval_result["complexity"] = pair["complexity"]
        results.append(eval_result)

        per_schema[pair["schema_name"]].append(eval_result)
        per_complexity[pair["complexity"]].append(eval_result)

        # Log individual result to W&B
        wandb.log({
            "bleu": eval_result["bleu"],
            "valid": int(eval_result["valid"]),
            "exec_success": int(eval_result["exec_success"]),
            "exec_match": int(eval_result["exec_match"]),
            "step": i + 1,
        })

        # Progress log every 10
        if (i + 1) % 10 == 0:
            so_far_ex = sum(r["exec_match"] for r in results) / len(results)
            so_far_valid = sum(r["exec_success"] for r in results) / len(results)
            log.info(
                "Progress",
                evaluated=i+1,
                ex_accuracy=f"{so_far_ex*100:.1f}%",
                validity=f"{so_far_valid*100:.1f}%",
            )

    # ── Final Metrics ────────────────────────────────────────────────────────
    n = len(results)
    overall = {
        "execution_accuracy": sum(r["exec_match"] for r in results) / n,
        "validity_rate": sum(r["exec_success"] for r in results) / n,
        "avg_bleu": sum(r["bleu"] for r in results) / n,
        "total_evaluated": n,
    }

    # Per-schema breakdown
    schema_metrics = {}
    for schema, schema_results in per_schema.items():
        ns = len(schema_results)
        schema_metrics[schema] = {
            "execution_accuracy": sum(r["exec_match"] for r in schema_results) / ns,
            "validity_rate": sum(r["exec_success"] for r in schema_results) / ns,
            "avg_bleu": sum(r["bleu"] for r in schema_results) / ns,
            "count": ns,
        }

    # Per-complexity breakdown
    complexity_metrics = {}
    for complexity, complexity_results in per_complexity.items():
        nc = len(complexity_results)
        complexity_metrics[complexity] = {
            "execution_accuracy": sum(r["exec_match"] for r in complexity_results) / nc,
            "validity_rate": sum(r["exec_success"] for r in complexity_results) / nc,
            "avg_bleu": sum(r["bleu"] for r in complexity_results) / nc,
            "count": nc,
        }

    # Log summary to W&B
    wandb.log({
        "final/execution_accuracy": overall["execution_accuracy"],
        "final/validity_rate": overall["validity_rate"],
        "final/avg_bleu": overall["avg_bleu"],
        **{f"schema/{s}/ex": v["execution_accuracy"] for s, v in schema_metrics.items()},
        **{f"complexity/{c}/ex": v["execution_accuracy"] for c, v in complexity_metrics.items()},
    })

    # Save detailed results as W&B artifact
    results_path = f"data/eval_{run_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(results_path, "w") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")

    artifact = wandb.Artifact(f"eval-results-{run_name}", type="evaluation")
    artifact.add_file(results_path)
    wandb.log_artifact(artifact)

    wandb.finish()

    # ── Print Summary ────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info(f"✅ Evaluation complete: {run_name}")
    log.info(f"   Execution Accuracy: {overall['execution_accuracy']*100:.1f}%")
    log.info(f"   Validity Rate:      {overall['validity_rate']*100:.1f}%")
    log.info(f"   Avg BLEU:           {overall['avg_bleu']:.4f}")
    log.info("")
    log.info("Per-schema breakdown:")
    for schema, m in sorted(schema_metrics.items()):
        log.info(f"   {schema}: EX={m['execution_accuracy']*100:.1f}% | Valid={m['validity_rate']*100:.1f}%")
    log.info("")
    log.info("Per-complexity breakdown:")
    for complexity, m in sorted(complexity_metrics.items()):
        log.info(f"   {complexity}: EX={m['execution_accuracy']*100:.1f}% | Valid={m['validity_rate']*100:.1f}%")

    return overall


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate OmniSQL on PostgreSQL test set")
    parser.add_argument("--mode", choices=["mock", "local", "sagemaker"], default="local")
    parser.add_argument("--run-name", default="omnisql-7b-baseline", help="W&B run name")
    parser.add_argument("--model-path", default=None, help="Path to fine-tuned model (optional)")
    parser.add_argument("--test-path", default=TEST_PATH, help="Path to test JSONL")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of test pairs (for quick testing)")
    args = parser.parse_args()

    asyncio.run(run_evaluation(
        mode=args.mode,
        run_name=args.run_name,
        model_path=args.model_path,
        test_path=args.test_path,
        limit=args.limit,
    ))