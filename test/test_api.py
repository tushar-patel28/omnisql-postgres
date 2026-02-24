"""
API Integration Tests
----------------------
Tests the full API layer with mocked database and services.
Run with: pytest tests/test_api.py -v
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health check should return 200 with status ok."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Mock DB init to avoid real DB connection
        with patch("app.core.database.init_db", new_callable=AsyncMock):
            response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "inference_mode" in data
    assert "database" in data


@pytest.mark.asyncio
async def test_query_returns_expected_fields():
    """Query endpoint should return all required response fields."""
    from app.main import app
    from app.core.models import SchemaRegistry

    mock_tables = [
        SchemaRegistry(
            schema_name="ecommerce",
            table_name="users",
            ddl="CREATE TABLE users (id SERIAL PRIMARY KEY)",
            description="Users",
            sample_values={},
        )
    ]

    with patch("app.core.database.init_db", new_callable=AsyncMock), \
         patch("app.api.routes.retrieve_relevant_tables", new_callable=AsyncMock, return_value=mock_tables), \
         patch("app.api.routes.run_inference", new_callable=AsyncMock, return_value=("SELECT COUNT(*) FROM users", "Count all users")), \
         patch("app.api.routes.execute_with_self_correction", new_callable=AsyncMock) as mock_exec, \
         patch("app.api.routes.log_query", new_callable=AsyncMock, return_value="test-query-id"), \
         patch("app.core.database.get_db"):

        from app.services.executor import ExecutionResult
        mock_exec.return_value = ExecutionResult(
            success=True,
            sql="SELECT COUNT(*) FROM users",
            original_sql="SELECT COUNT(*) FROM users",
            rows=[{"count": 42}],
            row_count=1,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/query",
                json={
                    "question": "How many users are there?",
                    "schema_name": "ecommerce",
                    "dialect": "postgresql",
                }
            )

    assert response.status_code == 200
    data = response.json()
    assert "query_id" in data
    assert "sql" in data
    assert "execution_success" in data
    assert "latency_ms" in data
    assert "inference_mode" in data
