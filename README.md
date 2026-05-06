# OmniSQL-Postgres

> Extending [OmniSQL-7B](https://arxiv.org/abs/2503.02240) (VLDB&apos;25 SOTA) to PostgreSQL via QLoRA fine-tuning, with a production MLOps pipeline on AWS.

[![Live Demo](https://img.shields.io/badge/Live_Demo-omnisql--postgres.vercel.app-6ea8ff?style=for-the-badge&logo=vercel&logoColor=white)](https://omnisql-postgres.vercel.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=for-the-badge)](https://www.python.org/downloads/)

---

## TL;DR

OmniSQL-7B is the current state-of-the-art text-to-SQL model (VLDB 2025), but the authors trained on SQLite syntax and explicitly call out the dialect gap as future work. This project closes that gap for PostgreSQL: synthesizing 2,000 execution-validated training pairs across 5 schemas, fine-tuning with QLoRA on SageMaker, and serving via an async inference endpoint behind a FastAPI service with pgvector RAG and self-correcting SQL execution.

**Headline result:** 6.6× improvement in execution accuracy on a 200-pair held-out test set.

| Metric | Baseline (OmniSQL-7B) | Fine-tuned (OmniSQL-Pg) | Δ |
|---|---:|---:|---:|
| Execution accuracy | 7.0% | **46.0%** | +39.0 pts |
| Validity rate | 15.0% | **94.0%** | +79.0 pts |
| Avg BLEU | 0.20 | **0.59** | +0.39 |

---

## Why this matters

The base OmniSQL-7B produces SQLite idioms — `julianday()`, `strftime()`, no schema namespacing — which fail outright against PostgreSQL. Fine-tuning teaches it the right dialect: `DATE_TRUNC`, `EXTRACT(... FROM ...)`, `INTERVAL`, schema-qualified table references. The 39-point execution-accuracy lift is attributable purely to dialect adaptation; the underlying reasoning ability of the base model is preserved.

Per-schema breakdown (fine-tuned vs baseline execution accuracy):

| Schema | Fine-tuned | Baseline |
|---|---:|---:|
| ecommerce | 30.0% | 7.5% |
| fintech | 53.8% | 15.4% |
| healthcare | 45.0% | 0.0% |
| hr_system | 43.9% | 7.3% |
| saas_analytics | 57.5% | 5.0% |

Per-complexity breakdown (fine-tuned only):

| Complexity | Execution accuracy |
|---|---:|
| Simple | 87.8% |
| Moderate | 42.9% |
| Complex | 31.5% |
| Highly complex | 25.7% |

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

## Project structure

```
.
├── app/                       # FastAPI service
│   ├── api/routes.py          # /query, /schemas, /feedback endpoints
│   ├── services/
│   │   ├── inference_client.py   # SageMaker async client (S3 in/out)
│   │   ├── executor.py        # SQL execution + self-correction
│   │   └── rag.py             # pgvector schema retrieval
│   └── main.py
├── infrastructure/            # Terraform modules
│   ├── vpc.tf  rds.tf  ecs.tf  sagemaker.tf  s3.tf  lambda.tf
│   └── variables.tf
├── scripts/
│   ├── inference/sagemaker_handler.py  # Server-side inference handler
│   ├── training/              # QLoRA fine-tuning scripts
│   ├── evaluation/evaluate.py # Execution-based eval harness
│   ├── synthetic/             # Training-pair generation
│   ├── deploy_sagemaker.py    # Model packaging + endpoint deployment
│   ├── setup_eval_db.py       # Eval database bootstrap
│   └── build_demo_data.py     # Generates frontend/src/lib/demo-data.ts
├── data/
│   ├── synthetic/pg_finetune.jsonl     # 1,800 train pairs
│   ├── synthetic/pg_test.jsonl         # 200 held-out test pairs
│   └── eval_*.jsonl                    # Saved eval runs (baseline + FT)
├── frontend/                  # Next.js + Tailwind demo UI
└── docker-compose.yml         # Local Postgres + pgvector
```

---

## Fine-tuning recipe

The full recipe is in `scripts/training/`. Headline numbers:

- **Base model:** [seeklhy/OmniSQL-7B](https://huggingface.co/seeklhy/OmniSQL-7B) (Qwen2 7B fine-tuned on SQLite text-to-SQL)
- **Method:** QLoRA, r=16, alpha=32, target modules `q_proj`, `k_proj`, `v_proj`, `o_proj`
- **Precision:** bf16 (fp16 produces token-0 contamination and NaN gradients on Qwen2 — bf16 is mandatory)
- **Optimizer:** AdamW, lr=1e-4, cosine schedule
- **Data:** 1,800 (question, schema_ddl, sql) pairs across 5 schemas, generated synthetically and execution-validated against real Postgres before being added to the training set
- **Hardware:** SageMaker `ml.g5.2xlarge`, 1 epoch, ~25 minutes
- **Adapter size:** 37 MB
- **Loss curve:** 0.7 → 0.18

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

### 2. Train and deploy the model

```bash
# Upload training data
aws s3 cp data/synthetic/pg_finetune.jsonl s3://<datasets-bucket>/train.jsonl

# Launch SageMaker training job (~25 min on ml.g5.2xlarge)
python scripts/training/launch_training_job.py

# Package and deploy to async endpoint
python scripts/deploy_sagemaker.py
```

### 3. Build and deploy the FastAPI service

```bash
cd ..
docker buildx build --platform linux/amd64 -t omnisql-api .
# Push to ECR + update ECS service (see scripts/deploy_api.sh)
```

### 4. Run the evaluation

```bash
python scripts/evaluation/evaluate.py \
  --endpoint omnisql-pg-endpoint \
  --test-set data/synthetic/pg_test.jsonl \
  --output data/eval_omnisql-pg-finetuned-full.jsonl
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

---

## Author

Tushar Vimalbhai Patel · MS Software Engineering, Northeastern University (2024-2026)

[![GitHub](https://img.shields.io/badge/GitHub-tushar--patel28-181717?style=flat&logo=github)](https://github.com/tushar-patel28)

---

## License

MIT