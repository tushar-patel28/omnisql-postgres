"""
Schema RAG Service
------------------
Embeds database schemas and retrieves relevant tables/columns
for a given natural language question using pgvector cosine similarity.

This is the core of making Text-to-SQL work on real databases with
hundreds of tables — we only pass relevant schema context to the model.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sentence_transformers import SentenceTransformer

from app.config import get_settings
from app.core.models import SchemaRegistry

log = structlog.get_logger()
settings = get_settings()

# Load embedding model once at module level (lazy init on first use)
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        log.info("Loading embedding model", model=settings.embedding_model)
        _embedding_model = SentenceTransformer(settings.embedding_model)
    return _embedding_model


def embed_text(text: str) -> list[float]:
    """Embed a string into a 384-dim vector using all-MiniLM-L6-v2."""
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def build_table_text(table: SchemaRegistry) -> str:
    """
    Build the text representation of a table for embedding.
    Combines table name, description, and column names from DDL.
    Richer text = better retrieval.
    """
    parts = [f"Table: {table.table_name}"]
    if table.description:
        parts.append(f"Description: {table.description}")
    parts.append(table.ddl)
    return "\n".join(parts)


async def register_schema(
    db: AsyncSession,
    schema_name: str,
    tables: list[dict],
) -> int:
    """
    Register a database schema into pgvector.
    Each table gets its own embedding row for fine-grained retrieval.

    Args:
        db: async database session
        schema_name: logical name (e.g. "ecommerce")
        tables: list of dicts with keys: table_name, ddl, description, sample_values

    Returns:
        Number of tables registered
    """
    # Delete existing entries for this schema (allow re-registration)
    await db.execute(
        text("DELETE FROM schema_registry WHERE schema_name = :name"),
        {"name": schema_name}
    )

    for table_data in tables:
        table_obj = SchemaRegistry(
            schema_name=schema_name,
            table_name=table_data["table_name"],
            ddl=table_data["ddl"],
            description=table_data.get("description"),
            sample_values=table_data.get("sample_values"),
        )

        # Build rich text and embed it
        table_text = build_table_text(table_obj)
        table_obj.embedding = embed_text(table_text)

        db.add(table_obj)

    await db.flush()
    log.info("Schema registered", schema=schema_name, table_count=len(tables))
    return len(tables)


async def retrieve_relevant_tables(
    db: AsyncSession,
    schema_name: str,
    question: str,
    top_k: int | None = None,
) -> list[SchemaRegistry]:
    """
    Find the most relevant tables for a question using cosine similarity.

    This is the RAG retrieval step — instead of dumping the entire schema
    into the prompt (which fails for large databases), we retrieve only
    the tables most likely needed to answer the question.

    Args:
        db: async session
        schema_name: which schema to search within
        question: natural language question
        top_k: number of tables to return (defaults to settings.rag_top_k)

    Returns:
        List of SchemaRegistry rows, ordered by relevance
    """
    k = top_k or settings.rag_top_k
    question_embedding = embed_text(question)

    # pgvector cosine distance operator: <=>
    # Lower distance = more similar
    result = await db.execute(
        select(SchemaRegistry)
        .where(SchemaRegistry.schema_name == schema_name)
        .order_by(SchemaRegistry.embedding.cosine_distance(question_embedding))
        .limit(k)
    )
    tables = result.scalars().all()

    log.info(
        "RAG retrieval complete",
        question=question[:60],
        schema=schema_name,
        tables_retrieved=[t.table_name for t in tables],
    )
    return list(tables)


def build_prompt(
    question: str,
    tables: list[SchemaRegistry],
    dialect: str = "postgresql",
) -> str:
    """
    Build the OmniSQL prompt from retrieved schema context.

    Follows OmniSQL's prompt template with:
    - DDL (CREATE TABLE statements)
    - Column descriptions via SQL comments
    - Sample values for value linking
    - Dialect tag
    - Chain-of-thought instruction

    This is what gets sent to the model.
    """
    # Build enriched DDL with sample values as comments
    schema_parts = []
    for table in tables:
        ddl = table.ddl.strip()

        # Inject sample values as comments for value linking
        if table.sample_values:
            value_comments = []
            for col, values in table.sample_values.items():
                sample_str = ", ".join(str(v) for v in values[:5])
                value_comments.append(f"-- {col} sample values: {sample_str}")
            if value_comments:
                ddl = ddl + "\n" + "\n".join(value_comments)

        if table.description:
            ddl = f"-- {table.description}\n{ddl}"

        schema_parts.append(ddl)

    db_details = "\n\n".join(schema_parts)

    prompt = f"""Task Overview:
You are a data science expert. Below, you are provided with a database schema and a natural language question. Your task is to understand the schema and generate a valid SQL query to answer the question.

Database Engine:
{dialect.upper()}

Database Schema:
{db_details}

This schema describes the database's structure, including tables, columns, primary keys, foreign keys, and any relevant relationships or constraints.

Question:
{question}

Instructions:
- Generate {dialect.upper()}-compatible SQL only. Use {dialect.upper()}-specific functions where appropriate (e.g., DATE_TRUNC, ILIKE, window functions).
- Make sure you only output the information asked in the question.
- The generated query should return all of the information asked without any missing or extra information.
- Before generating the final SQL query, think through the steps of how to write the query.

Output Format:
In your answer, please enclose the generated SQL query in a code block:
```sql
-- Your SQL query
```

Take a deep breath and think step by step to find the correct {dialect.upper()} SQL query."""

    return prompt
