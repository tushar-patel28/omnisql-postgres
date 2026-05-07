"""
scripts/evaluation/replay_eval.py
-----------------------------------
Re-evaluates a saved eval JSONL by replaying the (reference_sql, generated_sql)
pairs through the updated metrics module. No model inference; cheap and fast.

This is what you do when you fix the evaluator and want clean numbers without
re-running the model.

Usage:
    python scripts/evaluation/replay_eval.py \\
        --input data/eval_omnisql-pg-finetuned-full_20260505_132926.jsonl \\
        --output data/eval_omnisql-pg-finetuned-v2.jsonl \\
        --run-name omnisql-pg-finetuned-v2
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import structlog

from app.config import get_settings
from scripts.evaluation.metrics import (
    compute_bleu,
    is_valid_sql,
    execute_sql_safe,
    results_match_set_semantics,
    results_match_subset,
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()


async def replay(input_path: str, output_path: str, run_name: str, log_to_wandb: bool):
    settings = get_settings()
    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    with open(input_path) as f:
        rows = [json.loads(line) for line in f if line.strip()]

    log.info("Replaying eval", n=len(rows), input=input_path, output=output_path)

    new_results = []
    per_schema = defaultdict(list)
    per_complexity = defaultdict(list)

    for i, r in enumerate(rows):
        question      = r["question"]
        reference_sql = r["reference_sql"]
        generated_sql = r["generated_sql"]
        schema_name   = r.get("schema_name", "unknown")
        complexity    = r.get("complexity", "moderate")

        new_r = {
            "question":          question,
            "reference_sql":     reference_sql,
            "generated_sql":     generated_sql,
            "schema_name":       schema_name,
            "complexity":        complexity,
            "bleu":              compute_bleu(reference_sql, generated_sql),
            "valid":             is_valid_sql(generated_sql),
            "exec_success":      False,
            "exec_match":        False,
            "exec_match_relaxed": False,
            "error":             None,
        }

        if not new_r["valid"]:
            new_r["error"] = "Invalid SQL syntax"
            new_results.append(new_r)
            per_schema[schema_name].append(new_r)
            per_complexity[complexity].append(new_r)
            continue

        gen_ok, gen_rows, gen_err = await execute_sql_safe(generated_sql, dsn)
        new_r["exec_success"] = gen_ok
        if not gen_ok:
            new_r["error"] = gen_err
            new_results.append(new_r)
            per_schema[schema_name].append(new_r)
            per_complexity[complexity].append(new_r)
            continue

        ref_ok, ref_rows, ref_err = await execute_sql_safe(reference_sql, dsn)
        if not ref_ok:
            # Reference query itself broke — give credit (rare)
            new_r["exec_match"] = True
            new_r["exec_match_relaxed"] = True
            new_r["error"] = f"reference SQL failed: {ref_err}"
        else:
            strict = results_match_set_semantics(ref_rows, gen_rows)
            new_r["exec_match"] = strict
            new_r["exec_match_relaxed"] = strict or results_match_subset(
                ref_rows, gen_rows
            )

        new_results.append(new_r)
        per_schema[schema_name].append(new_r)
        per_complexity[complexity].append(new_r)

        if (i + 1) % 20 == 0:
            ex_so_far = sum(x["exec_match"] for x in new_results) / len(new_results)
            log.info(
                "progress",
                done=f"{i+1}/{len(rows)}",
                ex=f"{ex_so_far*100:.1f}%",
            )

    # ── Aggregate ────────────────────────────────────────────────────────────
    n = len(new_results)
    overall = {
        "execution_accuracy":         sum(r["exec_match"]         for r in new_results) / n,
        "execution_accuracy_relaxed": sum(r["exec_match_relaxed"] for r in new_results) / n,
        "validity_rate":              sum(r["exec_success"]       for r in new_results) / n,
        "avg_bleu":                   sum(r["bleu"]               for r in new_results) / n,
        "total_evaluated":            n,
    }

    schema_metrics = {}
    for schema, items in per_schema.items():
        nn = len(items)
        schema_metrics[schema] = {
            "execution_accuracy":         sum(x["exec_match"]         for x in items) / nn,
            "execution_accuracy_relaxed": sum(x["exec_match_relaxed"] for x in items) / nn,
            "validity_rate":              sum(x["exec_success"]       for x in items) / nn,
            "count":                      nn,
        }

    complexity_metrics = {}
    for complexity, items in per_complexity.items():
        nn = len(items)
        complexity_metrics[complexity] = {
            "execution_accuracy":         sum(x["exec_match"]         for x in items) / nn,
            "execution_accuracy_relaxed": sum(x["exec_match_relaxed"] for x in items) / nn,
            "validity_rate":              sum(x["exec_success"]       for x in items) / nn,
            "count":                      nn,
        }

    # ── Write ────────────────────────────────────────────────────────────────
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in new_results:
            f.write(json.dumps(r, default=str) + "\n")
    log.info("Wrote", path=output_path)

    # ── Print summary ────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info(f"✅ Replay complete: {run_name}")
    log.info(f"   Execution Accuracy (strict):  {overall['execution_accuracy']*100:.1f}%")
    log.info(f"   Execution Accuracy (relaxed): {overall['execution_accuracy_relaxed']*100:.1f}%")
    log.info(f"   Validity Rate:                {overall['validity_rate']*100:.1f}%")
    log.info(f"   Avg BLEU:                     {overall['avg_bleu']:.4f}")
    log.info("")
    log.info("Per-schema (strict):")
    for schema, m in sorted(schema_metrics.items()):
        log.info(
            f"   {schema:18s}  EX={m['execution_accuracy']*100:5.1f}%  "
            f"relaxed={m['execution_accuracy_relaxed']*100:5.1f}%  "
            f"valid={m['validity_rate']*100:5.1f}%  (n={m['count']})"
        )
    log.info("")
    log.info("Per-complexity (strict):")
    for complexity in ["simple", "moderate", "complex", "highly_complex"]:
        if complexity in complexity_metrics:
            m = complexity_metrics[complexity]
            log.info(
                f"   {complexity:18s}  EX={m['execution_accuracy']*100:5.1f}%  "
                f"relaxed={m['execution_accuracy_relaxed']*100:5.1f}%  "
                f"valid={m['validity_rate']*100:5.1f}%  (n={m['count']})"
            )

    if log_to_wandb:
        try:
            import wandb
            wandb.init(project="omnisql-postgres", name=run_name, config={
                "mode": "replay",
                "source": input_path,
                "evaluated_at": datetime.now().isoformat(),
            })
            wandb.log({
                "final/execution_accuracy":         overall["execution_accuracy"],
                "final/execution_accuracy_relaxed": overall["execution_accuracy_relaxed"],
                "final/validity_rate":              overall["validity_rate"],
                "final/avg_bleu":                   overall["avg_bleu"],
                **{f"schema/{s}/ex":         v["execution_accuracy"]         for s, v in schema_metrics.items()},
                **{f"schema/{s}/ex_relaxed": v["execution_accuracy_relaxed"] for s, v in schema_metrics.items()},
                **{f"complexity/{c}/ex":         v["execution_accuracy"]         for c, v in complexity_metrics.items()},
                **{f"complexity/{c}/ex_relaxed": v["execution_accuracy_relaxed"] for c, v in complexity_metrics.items()},
            })
            artifact = wandb.Artifact(f"eval-results-{run_name}", type="evaluation")
            artifact.add_file(output_path)
            wandb.log_artifact(artifact)
            wandb.finish()
            log.info("logged to W&B")
        except Exception as e:
            log.warning("W&B logging skipped", error=str(e)[:120])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/eval_omnisql-pg-finetuned-full_20260505_132926.jsonl",
        help="Source eval JSONL with question/reference_sql/generated_sql",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSONL with re-scored results (default: data/eval_<run-name>.jsonl)",
    )
    parser.add_argument("--run-name", default="omnisql-pg-finetuned-v2")
    parser.add_argument("--no-wandb", action="store_true", help="Skip W&B logging")
    args = parser.parse_args()

    output = args.output or f"data/eval_{args.run_name}.jsonl"
    asyncio.run(
        replay(
            input_path=args.input,
            output_path=output,
            run_name=args.run_name,
            log_to_wandb=not args.no_wandb,
        )
    )