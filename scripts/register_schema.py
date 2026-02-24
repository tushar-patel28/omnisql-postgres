"""
scripts/register_schema.py
---------------------------
Registers a sample e-commerce schema into pgvector.
This gives you something to immediately test queries against.

Usage:
    python scripts/register_schema.py
"""

import asyncio
import sys
import httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()

BASE_URL = "http://localhost:8000"

# ── Sample E-Commerce Schema ─────────────────────────────────────────────────
# A realistic schema with foreign keys, timestamps, and varied column types.
# Sample values are included for value linking (helps model understand actual data).

ECOMMERCE_SCHEMA = {
    "schema_name": "ecommerce",
    "tables": [
        {
            "table_name": "users",
            "description": "Registered users of the platform",
            "ddl": """CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE NOT NULL,
    name        VARCHAR(100) NOT NULL,
    tier        VARCHAR(20) DEFAULT 'standard',
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active   BOOLEAN DEFAULT TRUE
)""",
            "sample_values": {
                "tier": ["standard", "premium", "enterprise"],
                "is_active": [True, False],
            }
        },
        {
            "table_name": "products",
            "description": "Product catalog with pricing and inventory",
            "ddl": """CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    category    VARCHAR(100),
    price       NUMERIC(10, 2) NOT NULL,
    stock       INTEGER DEFAULT 0,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)""",
            "sample_values": {
                "category": ["electronics", "clothing", "books", "home", "sports"],
            }
        },
        {
            "table_name": "orders",
            "description": "Customer orders with status tracking",
            "ddl": """CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    status      VARCHAR(20) DEFAULT 'pending',
    total       NUMERIC(10, 2) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    shipped_at  TIMESTAMP WITH TIME ZONE
)""",
            "sample_values": {
                "status": ["pending", "processing", "shipped", "delivered", "cancelled"],
            }
        },
        {
            "table_name": "order_items",
            "description": "Individual line items within an order",
            "ddl": """CREATE TABLE order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL,
    unit_price  NUMERIC(10, 2) NOT NULL
)""",
            "sample_values": {}
        },
    ]
}


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Check API is running
        log.info("Checking API health...")
        try:
            resp = await client.get(f"{BASE_URL}/health")
            resp.raise_for_status()
            log.info("✅ API is running", response=resp.json())
        except Exception as e:
            log.error("❌ API not reachable", error=str(e))
            log.error("   Make sure the API is running: uvicorn app.main:app --reload")
            sys.exit(1)

        # 2. Register the schema
        log.info("Registering ecommerce schema...")
        resp = await client.post(
            f"{BASE_URL}/api/v1/schemas",
            json=ECOMMERCE_SCHEMA,
        )
        resp.raise_for_status()
        result = resp.json()
        log.info("✅ Schema registered", result=result)

        # 3. Test a sample query
        log.info("Testing a sample query...")
        resp = await client.post(
            f"{BASE_URL}/api/v1/query",
            json={
                "question": "How many users signed up this month?",
                "schema_name": "ecommerce",
                "dialect": "postgresql",
            }
        )
        resp.raise_for_status()
        query_result = resp.json()

        log.info("✅ Query successful!")
        log.info(f"   Question: {query_result['question']}")
        log.info(f"   SQL:      {query_result['sql']}")
        log.info(f"   Success:  {query_result['execution_success']}")
        log.info(f"   Latency:  {query_result['latency_ms']}ms")
        log.info(f"   Mode:     {query_result['inference_mode']}")
        log.info("")
        log.info("🚀 Phase 1 is working! Try more queries:")
        log.info("   curl -X POST http://localhost:8000/api/v1/query \\")
        log.info('     -H "Content-Type: application/json" \\')
        log.info('     -d \'{"question": "Show me the top 5 products by revenue", "schema_name": "ecommerce", "dialect": "postgresql"}\'')


if __name__ == "__main__":
    asyncio.run(main())
