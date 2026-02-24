"""
Query Logging Service
----------------------
Logs every query for monitoring, feedback collection, and retraining.

Every failed query that gets logged here becomes a candidate for the
retraining pipeline in Phase 5 — this is where the MLOps loop starts.
"""

import uuid
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.models import QueryLog

log = structlog.get_logger()


def generate_query_id() -> str:
    return str(uuid.uuid4())


async def log_query(
    db: AsyncSession,
    schema_name: str,
    question: str,
    generated_sql: str | None,
    dialect: str,
    execution_success: bool | None,
    execution_error: str | None,
    correction_attempts: int,
    final_sql: str | None,
    row_count: int | None,
    latency_ms: float,
    inference_mode: str,
    query_id: str | None = None,
) -> str:
    """
    Log a completed query to the database.
    Returns the query_id for reference in the API response.
    """
    qid = query_id or generate_query_id()

    entry = QueryLog(
        query_id=qid,
        schema_name=schema_name,
        question=question,
        generated_sql=generated_sql,
        dialect=dialect,
        execution_success=execution_success,
        execution_error=execution_error[:500] if execution_error else None,
        correction_attempts=correction_attempts,
        final_sql=final_sql,
        row_count=row_count,
        latency_ms=latency_ms,
        inference_mode=inference_mode,
    )

    db.add(entry)
    await db.flush()

    log.info(
        "Query logged",
        query_id=qid,
        success=execution_success,
        correction_attempts=correction_attempts,
        latency_ms=round(latency_ms, 1),
    )

    return qid


async def update_feedback(
    db: AsyncSession,
    query_id: str,
    feedback: int,
) -> bool:
    """
    Update user feedback for a logged query.
    feedback: 1 = thumbs up, -1 = thumbs down
    Returns True if query was found and updated.
    """
    result = await db.execute(
        select(QueryLog).where(QueryLog.query_id == query_id)
    )
    entry = result.scalar_one_or_none()

    if not entry:
        return False

    entry.user_feedback = feedback
    await db.flush()

    log.info("Feedback recorded", query_id=query_id, feedback=feedback)
    return True


async def get_recent_logs(
    db: AsyncSession,
    limit: int = 50,
    schema_name: str | None = None,
    failures_only: bool = False,
) -> list[QueryLog]:
    """
    Retrieve recent query logs.
    Used for monitoring and identifying candidates for retraining.
    """
    query = select(QueryLog).order_by(desc(QueryLog.created_at)).limit(limit)

    if schema_name:
        query = query.where(QueryLog.schema_name == schema_name)

    if failures_only:
        query = query.where(QueryLog.execution_success == False)  # noqa: E712

    result = await db.execute(query)
    return result.scalars().all()
