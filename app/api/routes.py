"""
API Routes
----------
All endpoints for the Text-to-SQL system.
"""

import time
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.models import SchemaRegistry, QueryLog
from app.config import get_settings
from app.api.schemas import (
    RegisterSchemaRequest, RegisterSchemaResponse,
    SchemaListItem, QueryRequest, QueryResponse,
    FeedbackRequest, FeedbackResponse,
    QueryLogItem,
)
from app.services.rag import register_schema, retrieve_relevant_tables, build_prompt
from app.services.inference import run_inference
from app.services.executor import execute_with_self_correction
from app.services.logger import log_query, update_feedback, get_recent_logs

log = structlog.get_logger()
settings = get_settings()

router = APIRouter(prefix="/api/v1")


# ── Schema Registration ──────────────────────────────────────────────────────

@router.post("/schemas", response_model=RegisterSchemaResponse)
async def register_schema_endpoint(
    request: RegisterSchemaRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a database schema for querying.
    Each table gets embedded into pgvector for RAG retrieval.
    """
    tables_data = [
        {
            "table_name": t.table_name,
            "ddl": t.ddl,
            "description": t.description,
            "sample_values": t.sample_values,
        }
        for t in request.tables
    ]

    count = await register_schema(db, request.schema_name, tables_data)

    return RegisterSchemaResponse(
        schema_name=request.schema_name,
        tables_registered=count,
        message=f"Successfully registered {count} tables for schema '{request.schema_name}'",
    )


@router.get("/schemas", response_model=list[SchemaListItem])
async def list_schemas(db: AsyncSession = Depends(get_db)):
    """List all registered schemas with table counts."""
    result = await db.execute(
        select(
            SchemaRegistry.schema_name,
            func.count(SchemaRegistry.id).label("table_count"),
            func.min(SchemaRegistry.created_at).label("created_at"),
        )
        .group_by(SchemaRegistry.schema_name)
        .order_by(SchemaRegistry.schema_name)
    )
    rows = result.all()

    return [
        SchemaListItem(
            schema_name=r.schema_name,
            table_count=r.table_count,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── Query ────────────────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Convert a natural language question to SQL and execute it.

    Full pipeline:
    1. RAG: retrieve relevant tables from pgvector
    2. Build OmniSQL prompt with schema context
    3. Run inference (mock/local/sagemaker)
    4. Execute SQL with self-correction
    5. Log everything for monitoring + retraining
    """
    start_time = time.monotonic()

    # 1. RAG: retrieve relevant schema context
    tables = await retrieve_relevant_tables(
        db, request.schema_name, request.question
    )

    if not tables:
        raise HTTPException(
            status_code=404,
            detail=f"Schema '{request.schema_name}' not found. Register it first via POST /api/v1/schemas",
        )

    # 2. Build prompt
    prompt = build_prompt(request.question, tables, request.dialect)

    # 3. Inference
    generated_sql, explanation = await run_inference(request.question, prompt)

    # 4. Execute with self-correction
    exec_result = await execute_with_self_correction(
        question=request.question,
        initial_sql=generated_sql,
        original_prompt=prompt,
        dialect=request.dialect,
    )

    latency_ms = (time.monotonic() - start_time) * 1000

    # 5. Log
    query_id = await log_query(
        db=db,
        schema_name=request.schema_name,
        question=request.question,
        generated_sql=generated_sql,
        dialect=request.dialect,
        execution_success=exec_result.success,
        execution_error=exec_result.error,
        correction_attempts=exec_result.correction_attempts,
        final_sql=exec_result.sql,
        row_count=exec_result.row_count,
        latency_ms=latency_ms,
        inference_mode=settings.inference_mode,
    )

    return QueryResponse(
        query_id=query_id,
        question=request.question,
        schema_name=request.schema_name,
        sql=exec_result.sql,
        explanation=explanation or None,
        execution_success=exec_result.success,
        results=exec_result.rows,
        row_count=exec_result.row_count,
        execution_error=exec_result.error,
        correction_attempts=exec_result.correction_attempts,
        latency_ms=round(latency_ms, 1),
        inference_mode=settings.inference_mode,
    )


# ── Feedback ─────────────────────────────────────────────────────────────────

@router.post("/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit thumbs up (1) or thumbs down (-1) for a query result."""
    if request.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="Feedback must be 1 (up) or -1 (down)")

    found = await update_feedback(db, request.query_id, request.feedback)

    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"Query ID '{request.query_id}' not found",
        )

    return FeedbackResponse(
        query_id=request.query_id,
        message="Feedback recorded. Thank you!",
    )


# ── Logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[QueryLogItem])
async def get_logs(
    limit: int = 50,
    schema_name: str | None = None,
    failures_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve query logs for monitoring.
    Use failures_only=true to see candidates for retraining.
    """
    logs = await get_recent_logs(db, limit=limit, schema_name=schema_name, failures_only=failures_only)
    return [QueryLogItem.model_validate(entry) for entry in logs]
