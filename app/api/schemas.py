from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


# ── Schema Registration ──────────────────────────────────────────────────────

class TableSchema(BaseModel):
    table_name: str
    ddl: str = Field(..., description="CREATE TABLE statement")
    description: Optional[str] = None
    sample_values: Optional[dict[str, list[Any]]] = Field(
        None,
        description="Sample column values for value linking. e.g. {'status': ['active', 'premium']}"
    )


class RegisterSchemaRequest(BaseModel):
    schema_name: str = Field(..., description="Logical name for this database schema")
    tables: list[TableSchema]


class RegisterSchemaResponse(BaseModel):
    schema_name: str
    tables_registered: int
    message: str


class SchemaListItem(BaseModel):
    schema_name: str
    table_count: int
    created_at: datetime


# ── Query ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., description="Natural language question")
    schema_name: str = Field(..., description="Which registered schema to query against")
    dialect: str = Field(default="postgresql", description="SQL dialect: postgresql | sqlite")


class QueryResponse(BaseModel):
    query_id: str
    question: str
    schema_name: str
    sql: str
    explanation: Optional[str] = None
    execution_success: bool
    results: Optional[list[dict]] = None
    row_count: Optional[int] = None
    execution_error: Optional[str] = None
    correction_attempts: int = 0
    latency_ms: float
    inference_mode: str


# ── Feedback ─────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    query_id: str
    feedback: int = Field(..., description="1 for thumbs up, -1 for thumbs down")


class FeedbackResponse(BaseModel):
    query_id: str
    message: str


# ── Logs ─────────────────────────────────────────────────────────────────────

class QueryLogItem(BaseModel):
    query_id: str
    schema_name: str
    question: str
    generated_sql: Optional[str]
    execution_success: Optional[bool]
    correction_attempts: int
    latency_ms: Optional[float]
    user_feedback: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    database: str
    inference_mode: str
    version: str = "0.1.0"
