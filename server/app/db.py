"""PostgreSQL connection pool (psycopg 3).

Every request takes a connection for a short time: `async with db.connection() as conn`.
Transactions are yours: `async with conn.transaction(): ...` (lab 1 and lab 2).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from . import config

_pool: AsyncConnectionPool | None = None


async def open_pool(size: int | None = None) -> None:
    """Open without waiting for the database: /health must answer even when it is down."""
    global _pool
    _pool = AsyncConnectionPool(
        config.DATABASE_URL,
        min_size=config.POOL_MIN,
        max_size=size or config.POOL_SIZE,
        timeout=config.POOL_TIMEOUT_S,
        kwargs={"row_factory": dict_row, "options": f"-c statement_timeout={config.STATEMENT_TIMEOUT_MS}"},
        open=False,
    )
    await _pool.open(wait=False)


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    if _pool is None:
        raise RuntimeError("database pool is not open")
    async with _pool.connection() as conn:
        yield conn


async def ping() -> bool:
    """For /ready: can this instance reach the database right now?"""
    try:
        async with connection() as conn:
            await conn.execute("SELECT 1")
        return True
    except (psycopg.Error, OSError):  # includes the pool timeout when the database is down
        return False
