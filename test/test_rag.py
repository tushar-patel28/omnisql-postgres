"""
Tests for the Schema RAG service.
Tests embedding, registration, retrieval, and prompt building.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag import (
    embed_text,
    build_table_text,
    build_prompt,
)
from app.core.models import SchemaRegistry


def test_embed_text_returns_correct_dimension():
    """all-MiniLM-L6-v2 produces 384-dim embeddings."""
    embedding = embed_text("show me all users")
    assert isinstance(embedding, list)
    assert len(embedding) == 384
    # Normalized embeddings are in [-1, 1]
    assert all(-1.0 <= v <= 1.0 for v in embedding)


def test_embed_text_different_inputs_produce_different_embeddings():
    """Different texts should produce different embeddings."""
    e1 = embed_text("show me all users")
    e2 = embed_text("what is the total revenue")
    assert e1 != e2


def test_build_table_text_includes_all_fields():
    """Table text for embedding should include name, description, and DDL."""
    table = SchemaRegistry(
        schema_name="test",
        table_name="orders",
        ddl="CREATE TABLE orders (id SERIAL PRIMARY KEY, total NUMERIC)",
        description="Customer orders",
    )
    text = build_table_text(table)
    assert "orders" in text
    assert "Customer orders" in text
    assert "CREATE TABLE" in text


def test_build_table_text_without_description():
    """Should work fine without a description."""
    table = SchemaRegistry(
        schema_name="test",
        table_name="products",
        ddl="CREATE TABLE products (id SERIAL PRIMARY KEY)",
        description=None,
    )
    text = build_table_text(table)
    assert "products" in text
    assert "CREATE TABLE" in text


def test_build_prompt_includes_dialect():
    """Prompt should explicitly state the SQL dialect."""
    tables = [
        SchemaRegistry(
            schema_name="ecommerce",
            table_name="users",
            ddl="CREATE TABLE users (id SERIAL PRIMARY KEY, email VARCHAR(255))",
            description="Platform users",
            sample_values={"email": ["user@example.com"]},
        )
    ]
    prompt = build_prompt("How many users are there?", tables, dialect="postgresql")
    assert "POSTGRESQL" in prompt
    assert "DATE_TRUNC" in prompt  # PostgreSQL-specific hint
    assert "ILIKE" in prompt
    assert "CREATE TABLE users" in prompt


def test_build_prompt_includes_sample_values():
    """Sample values should appear in prompt for value linking."""
    tables = [
        SchemaRegistry(
            schema_name="ecommerce",
            table_name="users",
            ddl="CREATE TABLE users (id SERIAL PRIMARY KEY, tier VARCHAR(20))",
            description=None,
            sample_values={"tier": ["standard", "premium", "enterprise"]},
        )
    ]
    prompt = build_prompt("Show me all premium users", tables, dialect="postgresql")
    assert "premium" in prompt
    assert "standard" in prompt


def test_build_prompt_with_multiple_tables():
    """Prompt should include DDL for all retrieved tables."""
    tables = [
        SchemaRegistry(
            schema_name="ecommerce",
            table_name="users",
            ddl="CREATE TABLE users (id SERIAL PRIMARY KEY)",
            description=None,
            sample_values=None,
        ),
        SchemaRegistry(
            schema_name="ecommerce",
            table_name="orders",
            ddl="CREATE TABLE orders (id SERIAL PRIMARY KEY, user_id INTEGER)",
            description=None,
            sample_values=None,
        ),
    ]
    prompt = build_prompt("How many orders per user?", tables, dialect="postgresql")
    assert "CREATE TABLE users" in prompt
    assert "CREATE TABLE orders" in prompt
