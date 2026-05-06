"""
scripts/setup_eval_db.py
-------------------------
Sets up all 5 test schemas in PostgreSQL with synthetic data.
Properly handles FK relationships, varchar lengths, and numeric precision.

Usage:
    python scripts/setup_eval_db.py
"""

import asyncio
import json
import random
import sys
from pathlib import Path
from datetime import datetime, timedelta

import asyncpg
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.config import get_settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()

TEST_PATH = "data/synthetic/pg_test.jsonl"
ROWS_PER_TABLE = 50
SEED = 42

APP_TABLES_TO_KEEP = {"schema_registry", "query_log"}

NAMESPACES = {
    "fintech": "fintech",
    "healthcare": "healthcare",
    "hr_system": "hr",
    "saas_analytics": "saas",
    "ecommerce": "public",
}


def get_unique_schemas(test_path: str) -> dict[str, str]:
    schemas = {}
    with open(test_path) as f:
        for line in f:
            d = json.loads(line)
            name = d["schema_name"]
            if name not in schemas:
                schemas[name] = d["schema_ddl"]
    return schemas


async def reset_database(conn, schema_names: list[str]):
    for name in schema_names:
        ns = NAMESPACES.get(name)
        if ns and ns != "public":
            await conn.execute(f"DROP SCHEMA IF EXISTS {ns} CASCADE")
            log.info(f"Dropped schema: {ns}")

    tables = await conn.fetch(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    dropped = 0
    for r in tables:
        if r["table_name"] not in APP_TABLES_TO_KEEP:
            await conn.execute(
                f'DROP TABLE IF EXISTS public."{r["table_name"]}" CASCADE'
            )
            dropped += 1
    log.info(f"Cleaned public schema: dropped {dropped} tables, kept app metadata")


async def create_schemas(conn, schemas: dict[str, str]):
    for name, ddl in schemas.items():
        try:
            await conn.execute(ddl)
            log.info(f"Created schema: {name}")
        except Exception as e:
            log.error(f"Failed to create {name}", error=str(e)[:200])
            raise


async def get_table_columns(conn, ns: str, tbl: str) -> list[dict]:
    cols = await conn.fetch(
        """
        SELECT column_name, data_type, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """,
        ns,
        tbl,
    )
    return [dict(c) for c in cols]


async def get_foreign_keys(conn, ns: str, tbl: str) -> dict:
    rows = await conn.fetch(
        """
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_schema,
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = $1
          AND tc.table_name = $2
        """,
        ns,
        tbl,
    )
    return {
        r["column_name"]: (
            r["foreign_schema"],
            r["foreign_table"],
            r["foreign_column"],
        )
        for r in rows
    }


async def get_existing_ids(conn, ns: str, tbl: str, col: str) -> list:
    full_name = f'"{ns}"."{tbl}"' if ns != "public" else f'"{tbl}"'
    try:
        rows = await conn.fetch(f"SELECT {col} FROM {full_name} LIMIT 100")
        return [r[col] for r in rows if r[col] is not None]
    except Exception:
        return []


def gen_value(col: dict, rng: random.Random):
    name = col["column_name"].lower()
    dtype = col["data_type"].lower()
    default = col["column_default"]
    max_len = col.get("character_maximum_length")

    if default and "nextval" in str(default):
        return None

    def fit(s: str) -> str:
        """Truncate string to column max length if applicable."""
        if max_len and len(s) > max_len:
            return s[:max_len]
        return s

    if "currency" in name:
        return rng.choice(["USD", "EUR", "GBP", "JPY", "CAD"])
    if "email" in name:
        return fit(f"u{rng.randint(1, 99999)}@x.com")
    if "name" in name:
        return fit(
            rng.choice(
                ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Henry",
                 "Ivy", "Jack", "Kate", "Liam", "Mia", "Noah", "Olivia"]
            )
        )
    if "status" in name:
        return fit(
            rng.choice(
                ["active", "pending", "completed", "cancelled", "closed", "shipped"]
            )
        )
    if "tier" in name:
        return fit(rng.choice(["standard", "premium", "enterprise"]))
    if "category" in name or "type" in name:
        return fit(rng.choice(["alpha", "beta", "gamma", "delta", "omega"]))
    if "title" in name:
        return fit(
            rng.choice(["Engineer", "Manager", "Analyst", "Director", "Lead"])
        )
    if "location" in name or "city" in name:
        return fit(rng.choice(["NYC", "SF", "Boston", "Austin", "Seattle"]))
    if name.startswith("is_") or dtype == "boolean":
        return rng.choice([True, False])

    if "int" in dtype or "smallint" in dtype or "bigint" in dtype:
        return rng.randint(1, 1000)
    if (
        "numeric" in dtype
        or "decimal" in dtype
        or "real" in dtype
        or "double" in dtype
    ):
        precision = col.get("numeric_precision")
        scale = col.get("numeric_scale") or 0
        if precision:
            # Fit within precision constraint: max integer part is 10^(precision-scale) - 1
            max_int_part = 10 ** (precision - scale) - 1
            value = rng.uniform(0, max_int_part)
            return round(value, scale)
        return round(rng.uniform(10, 5000), 2)
    if "timestamp" in dtype or "date" in dtype:
        days_ago = rng.randint(0, 365)
        return datetime.now() - timedelta(days=days_ago)
    if (
        "varchar" in dtype
        or "text" in dtype
        or "char" in dtype
        or "uuid" in dtype
    ):
        return fit(f"v_{rng.randint(1, 9999)}")
    if "json" in dtype:
        return json.dumps({"k": rng.randint(1, 100)})
    return None


def topo_sort_tables(tables_with_fks: list) -> list:
    name_to_fks = {n: f for n, f in tables_with_fks}
    remaining = set(name_to_fks)
    sorted_order = []

    while remaining:
        ready = []
        for tbl in remaining:
            fks = name_to_fks[tbl]
            deps = {
                target_tbl
                for col, (_, target_tbl, _) in fks.items()
                if target_tbl != tbl and target_tbl in remaining
            }
            if not deps:
                ready.append(tbl)

        if not ready:
            ready = [next(iter(remaining))]

        for t in ready:
            sorted_order.append(t)
            remaining.discard(t)

    return sorted_order


async def populate_schema(conn, schema_name: str, ns: str, rng: random.Random):
    table_rows = await conn.fetch(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = $1 AND table_type = 'BASE TABLE'
          AND table_name NOT IN ('schema_registry', 'query_log')
        """,
        ns,
    )
    tables = [r["table_name"] for r in table_rows]

    tables_with_fks = []
    for tbl in tables:
        fks = await get_foreign_keys(conn, ns, tbl)
        tables_with_fks.append((tbl, fks))

    sorted_tables = topo_sort_tables(tables_with_fks)
    log.info(f"Populating {schema_name} ({ns}): {sorted_tables}")

    fk_map = {n: f for n, f in tables_with_fks}

    for tbl in sorted_tables:
        fks = fk_map[tbl]
        cols = await get_table_columns(conn, ns, tbl)
        full_name = f'"{ns}"."{tbl}"' if ns != "public" else f'"{tbl}"'

        insertable = [
            c
            for c in cols
            if not (c["column_default"] and "nextval" in str(c["column_default"]))
        ]
        if not insertable:
            continue

        fk_values = {}
        for col_name, (target_schema, target_tbl, target_col) in fks.items():
            existing = await get_existing_ids(conn, target_schema, target_tbl, target_col)
            fk_values[col_name] = existing

        col_names = [c["column_name"] for c in insertable]
        placeholders = [f"${i+1}" for i in range(len(insertable))]
        sql = (
            f"INSERT INTO {full_name} ({', '.join(col_names)}) "
            f"VALUES ({', '.join(placeholders)}) "
            f"ON CONFLICT DO NOTHING"
        )

        inserted = 0
        for _ in range(ROWS_PER_TABLE):
            values = []
            for c in insertable:
                col_name = c["column_name"]
                if col_name in fks:
                    candidates = fk_values.get(col_name, [])
                    if candidates and (c["is_nullable"] == "NO" or rng.random() < 0.8):
                        values.append(rng.choice(candidates))
                    else:
                        values.append(None)
                else:
                    values.append(gen_value(c, rng))
            try:
                await conn.execute(sql, *values)
                inserted += 1
            except Exception:
                continue
        log.info(f"  {ns}.{tbl}: ~{inserted} rows")


async def main():
    settings = get_settings()
    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    log.info("Connecting to PostgreSQL", host=settings.postgres_host)

    schemas = get_unique_schemas(TEST_PATH)
    log.info(f"Found {len(schemas)} unique test schemas: {sorted(schemas)}")

    ssl = "require" if settings.postgres_host != "localhost" else None
    conn = await asyncpg.connect(dsn, ssl=ssl)
    try:
        await reset_database(conn, list(schemas))
        await create_schemas(conn, schemas)
        rng = random.Random(SEED)
        for name in schemas:
            ns = NAMESPACES[name]
            await populate_schema(conn, name, ns, rng)
        log.info("Setup complete!")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())