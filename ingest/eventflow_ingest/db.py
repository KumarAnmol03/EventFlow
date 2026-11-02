"""PostgreSQL connection pool and a minimal forward-only migration runner."""

from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
# Arbitrary constant: every ingest instance uses the same advisory-lock id,
# so concurrent startups apply migrations one at a time.
MIGRATION_LOCK_ID = 7_212_650_312


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url, min_size=1, max_size=10, command_timeout=10)


async def apply_migrations(pool: asyncpg.Pool) -> list[str]:
    """Apply every migrations/*.sql not yet recorded, in filename order, in one transaction.

    Returns the names of the migrations applied by this call.
    """
    applied_now: list[str] = []
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", MIGRATION_LOCK_ID)
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        done = {row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            await conn.execute(path.read_text())
            await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", path.name)
            applied_now.append(path.name)
    return applied_now
