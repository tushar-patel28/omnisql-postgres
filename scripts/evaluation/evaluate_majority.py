"""
scripts/evaluation/evaluate_majority.py
-----------------------------------------
Majority-voting evaluation (Maj@K). For each test question:

  1. Sample K completions with do_sample=True, temperature=0.7
  2. Extract SQL from each
  3. Execute each against Postgres
  4. Group by hash of result-set (set semantics)
  5. The most-common result-set wins (ties: earliest sample)
  6. Compare winner against reference

This is the standard reporting protocol for Text-to-SQL benchmarks (OmniSQL,
BIRD, Spider). It's ~K× the inference cost but typically lifts EX by 3-5
points over greedy / beam search.

Usage:
    python scripts/evaluation/evaluate_majority.py \\
        --run-name omnisql-pg-v3-maj8 \\
        --k 8 \\
        --temperature 0.7 \\
        --test-path data/synthetic/pg_test.jsonl
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import structlog
import wandb

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import get_settings
from app.services.inference_client import extract_sql_from_response
from scripts.evaluation.metrics import (
    compute_bleu,
    is_valid_sql,
    execute_sql_safe,
    results_match_set_semantics,
    results_match_subset,
    _row_to_value_tuple,
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()


def rows_hash(rows: list | None) -> str:
    """Hash the result rows in a set-semantics-compatible way."""
    if rows is None:
        return "ERROR"
    if not rows:
        return "EMPTY"
    tuples = sorted((_row_to_value_tuple(r) for r in rows), key=lambda t: str(t))
    return hashlib.md5(repr(tuples).encode()).hexdigest()


async def sample_one(
    bucket: str,
    region: str,
    endpoint: str,
    prompt: str,
    temperature: float,
    top_p: float,
    timeout_seconds: int = 300,
) -> str:
    """
    Send one sampling request to the SageMaker async endpoint.
    Returns the generated text (raw model output, before SQL extraction).
    """
    import boto3
    import uuid
    import time

    sm = boto3.client("sagemaker-runtime", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    request_id = uuid.uuid4().hex[:12]
    input_key = f"inference-inputs/maj_{request_id}.json"
    payload = json.dumps({
        "prompt": prompt,
        "max_new_tokens": 256,
        "do_sample": True,
        "temperature": temperature,
        "top_p": top_p,
    })
    s3.put_object(Bucket=bucket, Key=input_key, Body=payload)

    response = sm.invoke_endpoint_async(
        EndpointName=endpoint,
        ContentType="application/json",
        InputLocation=f"s3://{bucket}/{input_key}",
    )
    output_key = response["OutputLocation"].replace(f"s3://{bucket}/", "")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            resp = s3.get_object(Bucket=bucket, Key=output_key)
            return json.loads(resp["Body"].read())["generated_text"]
        except Exception:
            await asyncio.sleep(3)
    raise RuntimeError(f"Inference timed out after {timeout_seconds}s")


async def sample_k_parallel(
    bucket: str,
    region: str,
    endpoint: str,
    prompt: str,
    k: int,
    temperature: float,
    top_p: float,
) -> list[str]:
    """Sample K completions in parallel from the async endpoint."""
    tasks = [
        sample_one(bucket, region, endpoint, prompt, temperature, top_p)
        for _ in range(k)
    ]
    return await asyncio.gather(*tasks, return_exceptions=True)


async def evaluate_one_question(
    bucket: str,
    region: str,
    endpoint: str,
    question: str,
    prompt: str,
    reference_sql: str,
    dsn: str,
    k: int,
    temperature: float,
    top_p: float,
) -> dict:
    """Run Maj@K voting for a single question."""
    # 1. Sample K completions in parallel
    raw_outputs = await sample_k_parallel(
        bucket, region, endpoint, prompt, k, temperature, top_p
    )

    # 2. Extract SQL from each
    samples = []
    for raw in raw_outputs:
        if isinstance(raw, Exception):
            samples.append({"raw": "", "sql": "", "error": str(raw)})
            continue
        sql, _explanation = extract_sql_from_response(raw)
        samples.append({"raw": raw, "sql": sql, "error": None})

    # 3. Execute each + hash the result-set
    for s in samples:
        if not s["sql"] or not is_valid_sql(s["sql"]):
            s["exec_success"] = False
            s["rows"] = None
            s["hash"] = "INVALID"
            continue
        ok, rows, err = await execute_sql_safe(s["sql"], dsn)
        s["exec_success"] = ok
        s["rows"] = rows if ok else None
        s["hash"] = rows_hash(rows) if ok else "ERROR"

    # 4. Vote: count valid (exec_success=True) hashes
    valid_hashes = [s["hash"] for s in samples if s["exec_success"]]
    counter = Counter(valid_hashes)

    if counter:
        winning_hash, _ = counter.most_common(1)[0]
        winner = next(s for s in samples if s["hash"] == winning_hash)
    else:
        # All samples failed to execute — fall back to first sample
        winner = samples[0]

    # 5. Compare winner's rows against reference
    ref_ok, ref_rows, ref_err = await execute_sql_safe(reference_sql, dsn)

    if winner["exec_success"] and ref_ok:
        strict = results_match_set_semantics(ref_rows, winner["rows"])
        relaxed = strict or results_match_subset(ref_rows, winner["rows"])
    elif not ref_ok:
        strict = True
        relaxed = True
    else:
        strict = False
        relaxed = False

    return {
        "question": question,
        "reference_sql": reference_sql,
        "generated_sql": winner["sql"],
        "bleu": compute_bleu(reference_sql, winner["sql"]),
        "valid": is_valid_sql(winner["sql"]),
        "exec_success": winner["exec_success"],
        "exec_match": strict,
        "exec_match_relaxed": relaxed,
        "k": k,
        "winning_vote_count": counter[winner["hash"]] if winner["exec_success"] else 0,
        "n_valid_samples": len(valid_hashes),
        "all_sample_sqls": [s["sql"][:300] for s in samples],
    }


async def main(args):
    settings = get_settings()
    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    bucket = "omnisql-dev-models-540659119855"
    region = settings.aws_region
    endpoint = settings.sagemaker_endpoint_name

    with open(args.test_path) as f:
        test_pairs = [json.loads(line) for line in f if line.strip()]
    if args.limit:
        test_pairs = test_pairs[: args.limit]

    log.info(
        "Starting Maj@K evaluation",
        run_name=args.run_name,
        k=args.k,
        temperature=args.temperature,
        top_p=args.top_p,
        n=len(test_pairs),
    )

    wandb.init(
        project="omnisql-postgres",
        name=args.run_name,
        config={
            "mode": "sagemaker-maj-vote",
            "k": args.k,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "test_path": args.test_path,
            "evaluated_at": datetime.now().isoformat(),
        },
    )

    results = []
    per_schema = defaultdict(list)
    per_complexity = defaultdict(list)

    for i, pair in enumerate(test_pairs):
        prompt = (
            f"### Schema:\n{pair['schema_ddl']}\n\n"
            f"### Question:\n{pair['question']}\n\n"
            f"### SQL:\n"
        )
        log.info(
            "Evaluating",
            i=f"{i+1}/{len(test_pairs)}",
            schema=pair["schema_name"],
            complexity=pair["complexity"],
        )
        try:
            r = await evaluate_one_question(
                bucket=bucket,
                region=region,
                endpoint=endpoint,
                question=pair["question"],
                prompt=prompt,
                reference_sql=pair["sql"],
                dsn=dsn,
                k=args.k,
                temperature=args.temperature,
                top_p=args.top_p,
            )
        except Exception as e:
            log.warning("Question failed", error=str(e)[:200])
            r = {
                "question": pair["question"],
                "reference_sql": pair["sql"],
                "generated_sql": "",
                "bleu": 0.0,
                "valid": False,
                "exec_success": False,
                "exec_match": False,
                "exec_match_relaxed": False,
                "error": str(e)[:400],
            }

        r["schema_name"] = pair["schema_name"]
        r["complexity"] = pair["complexity"]
        results.append(r)
        per_schema[pair["schema_name"]].append(r)
        per_complexity[pair["complexity"]].append(r)

        wandb.log({
            "step": i + 1,
            "exec_match": int(r["exec_match"]),
            "exec_match_relaxed": int(r["exec_match_relaxed"]),
            "exec_success": int(r["exec_success"]),
            "valid": int(r["valid"]),
            "bleu": r["bleu"],
            "winning_vote_count": r.get("winning_vote_count", 0),
        })

        if (i + 1) % 5 == 0:
            ex = sum(x["exec_match"] for x in results) / len(results)
            log.info("Progress", done=i + 1, ex=f"{ex*100:.1f}%")

    # ── Aggregate ────────────────────────────────────────────────────────────
    n = len(results)
    overall = {
        "execution_accuracy":         sum(r["exec_match"] for r in results) / n,
        "execution_accuracy_relaxed": sum(r["exec_match_relaxed"] for r in results) / n,
        "validity_rate":              sum(r["exec_success"] for r in results) / n,
        "avg_bleu":                   sum(r["bleu"] for r in results) / n,
        "total_evaluated":            n,
    }
    schema_metrics = {
        s: {
            "execution_accuracy":         sum(r["exec_match"] for r in items) / len(items),
            "execution_accuracy_relaxed": sum(r["exec_match_relaxed"] for r in items) / len(items),
            "validity_rate":              sum(r["exec_success"] for r in items) / len(items),
            "count":                      len(items),
        }
        for s, items in per_schema.items()
    }
    complexity_metrics = {
        c: {
            "execution_accuracy":         sum(r["exec_match"] for r in items) / len(items),
            "execution_accuracy_relaxed": sum(r["exec_match_relaxed"] for r in items) / len(items),
            "validity_rate":              sum(r["exec_success"] for r in items) / len(items),
            "count":                      len(items),
        }
        for c, items in per_complexity.items()
    }

    # ── Write ────────────────────────────────────────────────────────────────
    output_path = f"data/eval_{args.run_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")
    log.info("Wrote", path=output_path)

    wandb.log({
        "final/execution_accuracy":         overall["execution_accuracy"],
        "final/execution_accuracy_relaxed": overall["execution_accuracy_relaxed"],
        "final/validity_rate":              overall["validity_rate"],
        "final/avg_bleu":                   overall["avg_bleu"],
        **{f"schema/{s}/ex":       v["execution_accuracy"]       for s, v in schema_metrics.items()},
        **{f"complexity/{c}/ex":   v["execution_accuracy"]       for c, v in complexity_metrics.items()},
    })
    artifact = wandb.Artifact(f"eval-results-{args.run_name}", type="evaluation")
    artifact.add_file(output_path)
    wandb.log_artifact(artifact)
    wandb.finish()

    log.info("=" * 60)
    log.info(f"✅ Maj@{args.k} eval complete: {args.run_name}")
    log.info(f"   Execution Accuracy (strict):  {overall['execution_accuracy']*100:.1f}%")
    log.info(f"   Execution Accuracy (relaxed): {overall['execution_accuracy_relaxed']*100:.1f}%")
    log.info(f"   Validity Rate:                {overall['validity_rate']*100:.1f}%")
    log.info(f"   Avg BLEU:                     {overall['avg_bleu']:.4f}")
    log.info("")
    log.info("Per-schema (strict):")
    for s, m in sorted(schema_metrics.items()):
        log.info(
            f"   {s:18s}  EX={m['execution_accuracy']*100:5.1f}%  "
            f"valid={m['validity_rate']*100:5.1f}%  (n={m['count']})"
        )
    log.info("")
    log.info("Per-complexity (strict):")
    for c in ["simple", "moderate", "complex", "highly_complex"]:
        if c in complexity_metrics:
            m = complexity_metrics[c]
            log.info(
                f"   {c:18s}  EX={m['execution_accuracy']*100:5.1f}%  "
                f"valid={m['validity_rate']*100:5.1f}%  (n={m['count']})"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", default="omnisql-pg-v3-maj8")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--test-path", default="data/synthetic/pg_test.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    asyncio.run(main(args))