from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class SchemaRegistry(Base):
    """
    Stores registered database schemas and their embeddings.
    Each row = one table within a schema, with its embedding for RAG retrieval.
    """
    __tablename__ = "schema_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    ddl: Mapped[str] = mapped_column(Text, nullable=False)          # CREATE TABLE statement
    description: Mapped[str] = mapped_column(Text, nullable=True)   # human description of table
    sample_values: Mapped[dict] = mapped_column(JSON, nullable=True) # {col: [val1, val2, ...]}
    embedding: Mapped[list] = mapped_column(Vector(384), nullable=True)  # all-MiniLM-L6-v2 dim
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<SchemaRegistry schema={self.schema_name} table={self.table_name}>"


class QueryLog(Base):
    """
    Logs every query end-to-end for feedback, monitoring, and retraining.
    """
    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    schema_name: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=True)
    dialect: Mapped[str] = mapped_column(String(20), default="postgresql")
    execution_success: Mapped[bool] = mapped_column(Boolean, nullable=True)
    execution_error: Mapped[str] = mapped_column(Text, nullable=True)
    correction_attempts: Mapped[int] = mapped_column(Integer, default=0)
    final_sql: Mapped[str] = mapped_column(Text, nullable=True)     # after self-correction
    row_count: Mapped[int] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=True)
    user_feedback: Mapped[int] = mapped_column(Integer, nullable=True)  # 1=thumbs up, -1=thumbs down
    inference_mode: Mapped[str] = mapped_column(String(20), nullable=True)  # mock/local/sagemaker
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<QueryLog id={self.query_id} success={self.execution_success}>"
