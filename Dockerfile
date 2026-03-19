FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# ML packages excluded — inference runs on SageMaker in production
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    "uvicorn[standard]==0.30.6" \
    pydantic==2.9.2 \
    pydantic-settings==2.5.2 \
    sqlalchemy==2.0.35 \
    asyncpg==0.29.0 \
    psycopg2-binary==2.9.9 \
    pgvector==0.3.5 \
    sentence-transformers==3.1.1 \
    sqlparse==0.5.1 \
    structlog==24.4.0 \
    boto3==1.35.0 \
    greenlet

# Copy application code
COPY app/ ./app/

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]