"""
scripts/init_db.py
------------------
Initializes PostgreSQL database with pgvector extension and creates all tables.
Run this once after starting docker-compose.

Usage:
    python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import init_db
from app.config import get_settings
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)

log = structlog.get_logger()


async def main():
    settings = get_settings()
    log.info(
        "Initializing database",
        host=settings.postgres_host,
        port=settings.postgres_port,
        db=settings.postgres_db,
    )

    try:
        await init_db()
        log.info("✅ Database initialized successfully")
        log.info("   - pgvector extension enabled")
        log.info("   - schema_registry table created")
        log.info("   - query_log table created")
        log.info("")
        log.info("Next step: python scripts/register_schema.py")
    except Exception as e:
        log.error("❌ Database initialization failed", error=str(e))
        log.error("   Make sure Docker is running: docker-compose up -d")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
