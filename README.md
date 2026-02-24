# PostgreSQL Text-to-SQL System
> Extending OmniSQL-7B (VLDB'25) to PostgreSQL with production MLOps pipeline on AWS.

## Project Overview
This system takes natural language questions and generates validated PostgreSQL queries using a fine-tuned OmniSQL-7B model with schema-aware RAG via pgvector.

## Architecture
```
User Question
     │
     ▼
FastAPI (/query)
     │
     ▼
Schema RAG (pgvector similarity search)
     │
     ▼
OmniSQL-7B Inference (local → SageMaker in prod)
     │
     ▼
SQL Execution + Self-Correction Engine
     │
     ▼
Results + Feedback Logging
```

## Phase 1 (Current) — Local Foundation
- FastAPI backend
- PostgreSQL + pgvector (Docker)
- Schema RAG layer
- SQLite execution engine (local demo)
- PostgreSQL execution engine
- Feedback logging

## Stack
- **API:** FastAPI, Pydantic, uvicorn
- **Database:** PostgreSQL + pgvector (Docker)
- **Embeddings:** sentence-transformers (all-MiniLM-L6-v2)
- **Inference:** OmniSQL-7B via HuggingFace Transformers (local)
- **Validation:** sqlparse
- **Logging:** structlog

## Quickstart

### 1. Prerequisites
- Docker Desktop running
- Python 3.11+
- ~16GB RAM (for OmniSQL-7B)

### 2. Start PostgreSQL + pgvector
```bash
docker-compose up -d
```

### 3. Setup Python environment
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your settings
```

### 5. Initialize database
```bash
python scripts/init_db.py
```

### 6. Register a sample schema
```bash
python scripts/register_schema.py
```

### 7. Run the API
```bash
uvicorn app.main:app --reload --port 8000
```

### 8. Test it
```bash
# Check health
curl http://localhost:8000/health

# List schemas
curl http://localhost:8000/api/v1/schemas

# Query (uses mock inference in Phase 1)
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many users signed up last month?", "schema_name": "ecommerce"}'
```

## API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/schemas` | List registered schemas |
| POST | `/api/v1/schemas` | Register a new schema |
| POST | `/api/v1/query` | Natural language → SQL |
| POST | `/api/v1/feedback` | Submit feedback on a result |
| GET | `/api/v1/logs` | Query execution logs |

## Project Structure
```
text2sql/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Settings (pydantic-settings)
│   ├── api/
│   │   ├── routes.py        # All API routes
│   │   └── schemas.py       # Pydantic request/response models
│   ├── core/
│   │   ├── database.py      # PostgreSQL connection + pgvector
│   │   └── models.py        # SQLAlchemy ORM models
│   └── services/
│       ├── rag.py           # Schema RAG (pgvector similarity)
│       ├── inference.py     # OmniSQL-7B inference (mock → real)
│       ├── executor.py      # SQL execution + self-correction
│       └── logger.py        # Query logging service
├── tests/
│   ├── test_rag.py
│   ├── test_executor.py
│   └── test_api.py
├── scripts/
│   ├── init_db.py           # DB init + pgvector extension
│   └── register_schema.py   # Register sample schemas
├── docker/
│   └── Dockerfile           # App Dockerfile (for later)
├── docker-compose.yml       # PostgreSQL + pgvector
├── requirements.txt
├── .env.example
└── README.md
```
