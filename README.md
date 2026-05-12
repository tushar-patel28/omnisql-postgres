# OmniSQL-Postgres

> Extending [OmniSQL-7B](https://arxiv.org/abs/2503.02240) (VLDB&apos;25 SOTA) to PostgreSQL via QLoRA fine-tuning, with a production MLOps pipeline on AWS.

[![Live Demo](https://img.shields.io/badge/Live_Demo-omnisql--postgres.vercel.app-6ea8ff?style=for-the-badge&logo=vercel&logoColor=white)](https://omnisql-postgres.vercel.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=for-the-badge)](https://www.python.org/downloads/)

---

## TL;DR

OmniSQL-7B is the current state-of-the-art text-to-SQL model (VLDB 2025), but the authors trained on SQLite syntax and explicitly call out the dialect gap as future work. This project closes that gap for PostgreSQL: synthesizing 2,400 execution-validated training pairs across 5 schemas, fine-tuning with QLoRA on SageMaker, and serving via an async inference endpoint behind a FastAPI service with pgvector RAG and self-correcting SQL execution.

**Headline result:** 2.9× improvement in execution accuracy over the zero-shot baseline, under matched decoding settings.

| Metric | Baseline (OmniSQL-7B) | Fine-tuned (OmniSQL-Pg) | Δ |
|---|---:|---:|---:|
| Execution accuracy | 23.0% | **66.0%** | +43.0 pts |
| Validity rate | 35.5% | **96.0%** | +60.5 pts |
| Avg BLEU | 0.33 | **0.61** | +0.28 |

Both numbers measured on a 200-pair held-out test set, beam-search decoding (`num_beams=4`), and set-semantics execution-accuracy comparison (the BIRD/Spider convention).

---

## Why this matters

The base OmniSQL-7B produces SQLite idioms — `julianday()`, `strftime()`, no schema namespacing — which fail outright against PostgreSQL. Fine-tuning teaches it the right dialect: `DATE_TRUNC`, `EXTRACT(... FROM ...)`, `INTERVAL`, schema-qualified table references. The 43-point execution-accuracy lift is attributable purely to dialect adaptation; the underlying reasoning ability of the base model is preserved.

Per-schema breakdown (fine-tuned vs baseline execution accuracy):

| Schema | Fine-tuned | Baseline |
|---|---:|---:|
| ecommerce | 45.0% | 30.0% |
| fintech | 76.9% | 28.2% |
| healthcare | 77.5% | 7.5% |
| hr_system | 58.5% | 29.3% |
| saas_analytics | 72.5% | 20.0% |

Per-complexity breakdown (fine-tuned only):

| Complexity | Execution accuracy |
|---|---:|
| Simple | 95.1% |
| Moderate | 70.0% |
| Complex | 53.7% |
| Highly complex | 42.9% |

---

## Iteration log

Each row is a single, attributable engineering change measured against the same 200-pair test set. Numbers are strict execution accuracy.

| Iteration | EX | What changed |
|---|---:|---|
| v1 (initial) | 46.0% | 1,800 generic synthetic pairs, greedy decoding, list-equality result comparison |
| v1 + fixed eval | 60.0% | Switched comparator to set semantics (order- and column-name independent), matching BIRD/Spider conventions. The original list-equality penalized cosmetic differences like row order and column aliases. |
| v2 retrain | 62.0% | Added 600 targeted pairs (list-with-detail, time-series, window functions, multi-join-filter) addressing identified failure modes. Retrained LoRA on 2,400 pairs. |
| v2 + beam=4 | **66.0%** | Beam search decoding (was greedy). Helps most on highly-complex queries (+8.6 pts) where the model needs to back out of a wrong early token. |

The baseline numbers in the headline table use the same beam=4 decoding for a fair comparison — beam search lifts the zero-shot baseline from 8% to 23% on its own. Even after that adjustment, fine-tuning contributes a clean +43 points.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  User Question                                              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI on ECS Fargate · ALB · TLS termination             │
│  (Pydantic validation, request routing)                     │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  pgvector RAG · top-K relevant tables for the question      │
│  (RDS Postgres + pgvector ext, OpenAI embeddings)           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  SageMaker async endpoint · ml.g5.2xlarge                   │
│  OmniSQL-7B base (frozen) + LoRA adapter (37 MB) · bf16     │
│  Beam search decoding (num_beams=4, configurable)           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  SQL Executor · validates against sandboxed Postgres        │
│  · self-corrects up to 2× on errors                         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
                   Validated SQL + JSON results
```

All AWS infrastructure is defined as Terraform single-file modules (`vpc.tf`, `ecs.tf`, `rds.tf`, `sagemaker.tf`, etc.) and can be torn down between work sessions to keep idle costs near zero.

---

## Fine-tuning recipe

The full recipe is in `scripts/train.py`. Headline numbers:

- **Base model:** [seeklhy/OmniSQL-7B](https://huggingface.co/seeklhy/OmniSQL-7B) (Qwen2 7B fine-tuned on SQLite text-to-SQL)
- **Method:** QLoRA, r=16, alpha=32, target modules `q_proj`, `k_proj`, `v_proj`, `o_proj`
- **Precision:** bf16 (fp16 produces token-0 contamination and NaN gradients on Qwen2 — bf16 is mandatory)
- **Optimizer:** AdamW, lr=1e-4, cosine schedule
- **Data:** 2,400 (question, schema_ddl, sql) pairs across 5 schemas — 1,800 generic pairs from Groq llama-3.3-70b + 600 pattern-targeted pairs from DeepSeek V3. All execution-validated against real Postgres before being added to the training set.
- **Hardware:** SageMaker `ml.g5.2xlarge`, 1 epoch, ~31 minutes
- **Adapter size:** 37 MB
- **Loss curve:** 0.65 → 0.17

The pre-eval validation step is the unsung hero of the data pipeline — every generated SQL pair is executed against a containerized Postgres with the relevant schema and discarded if it doesn't run. Without it, the training set is full of plausible-looking but broken SQL.

---

## Live demo

🔗 **[omnisql-postgres.vercel.app](https://omnisql-postgres.vercel.app)**

The demo replays pre-recorded outputs from the real fine-tuned model to keep hosting at $0. Every example you see is an actual prediction from the model on a held-out test question — including the SQL, the BLEU score, and the execution-match flag. The result rows are heuristically synthesized from the SQL shape since running the live executor would require keeping infrastructure online.

To run the actual model end-to-end, see the deployment section below.

---

## Running it yourself

### Prerequisites
- AWS account with SageMaker, ECS, RDS, S3 access
- Terraform 1.6+
- Docker Desktop
- Python 3.11+
- Node.js 20+ (for the frontend)

### 1. Provision infrastructure

```bash
cd infrastructure
terraform init
terraform apply
```

This creates: VPC + subnets, RDS Postgres with pgvector, ECR repos, ECS Fargate cluster, SageMaker IAM role, S3 buckets for models / inference / datasets.

For training-only experimentation you can target a subset and skip ECS/RDS:

```bash
terraform apply -target=module.s3 -target=module.sagemaker
```

### 2. Train and deploy the model

```bash
# Upload training data
aws s3 cp data/synthetic/pg_finetune_v2_combined.jsonl \
  s3://<datasets-bucket>/pg_finetune_v2_combined.jsonl

# Launch SageMaker training job (~31 min on ml.g5.2xlarge)
python scripts/launch_training.py

# Package and deploy to async endpoint (auto-detects latest training job)
python scripts/deploy_sagemaker.py --version omnisql-pg-v2
```

### 3. Build and deploy the FastAPI service

```bash
cd ..
docker buildx build --platform linux/amd64 -t omnisql-api .
# Push to ECR + update ECS service (see scripts/deploy.sh)
```

### 4. Run the evaluation

```bash
python scripts/evaluation/evaluate.py \
  --mode sagemaker \
  --run-name omnisql-pg-v2-beam4 \
  --test-path data/synthetic/pg_test.jsonl
```

### 5. (Optional) Run the frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3030
```

### 6. Tear it all down

```bash
cd infrastructure
terraform destroy
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Base model | OmniSQL-7B (Qwen2 architecture) |
| Fine-tuning | PEFT (QLoRA), bitsandbytes, transformers |
| Inference | SageMaker async endpoints, HuggingFace inference container |
| Decoding | Beam search (`num_beams=4`), bf16 |
| Synthetic data | Groq llama-3.3-70b (generic), DeepSeek V3 (targeted patterns) |
| API | FastAPI, Pydantic, SQLAlchemy, structlog |
| Vector store | RDS Postgres + pgvector |
| Embeddings | OpenAI `text-embedding-3-small` |
| Container orchestration | ECS Fargate behind ALB |
| Infrastructure as code | Terraform |
| Experiment tracking | Weights & Biases |
| Frontend | Next.js 16, TypeScript, Tailwind v4, shadcn/ui |
| Hosting (frontend) | Vercel |

---

## Engineering notes

A few things worth pulling out for anyone building similar systems:

- **`bf16` not `fp16` for Qwen2.** fp16 inference produces token-0 (`!`) contamination, and fp16 training produces NaN gradients. This is a hard requirement, not an optimization.
- **Mask prompt tokens with -100.** Train only on the answer span. Without this, the model is rewarded for memorizing schema text.
- **Use `default_data_collator` and stock `Trainer`.** Not `SFTTrainer`. The HF trainer does the right thing for causal LM with already-masked labels.
- **`add_special_tokens=False` on the full tokenized sequence.** Otherwise the prompt-mask boundary drifts by one token and you train on partially-correct labels for thousands of examples.
- **HuggingFace inference containers max out at `transformers==4.37`** in `us-east-1`. Qwen2Tokenizer requires ≥4.37, so you're on the edge. Use a plain PyTorch container with a bootstrap `pip install` if you need newer libraries.
- **`/opt/ml/model/` is read-only at inference time.** Copy adapter config to `/tmp/peft_model/` first or PEFT will throw.
- **Set-semantics result comparison.** Comparing result rows as ordered lists with named columns (the obvious first cut) penalizes the model for cosmetic differences — different row order, different column aliases. BIRD/Spider compare result sets as multisets of value-tuples. Switching to that convention in `scripts/evaluation/metrics.py` lifted measured EX by 14 points on the same model.
- **Beam search > greedy for structured outputs.** Greedy commits to whatever the top-1 token is at each step; if that token is wrong (e.g. a SQLite idiom for the baseline, or a hallucinated column name), the whole completion is unrecoverable. Beam=4 with `early_stopping=True` was a +4 EX win on the fine-tuned model and a +15 EX win on the baseline.

---

## Author

Tushar Vimalbhai Patel · MS Software Engineering, Northeastern University (2024-2026)

[![GitHub](https://img.shields.io/badge/GitHub-tushar--patel28-181717?style=flat&logo=github)](https://github.com/tushar-patel28)

---

## License

MIT
