"""PostgreSQL / PostGIS async connection pool and query helpers.

Every other backend file imports from here:
    from db import get_pool, close_pool, fetch, fetchrow, fetchval, execute, serialize_row
"""

import os
from typing import Any, Optional
import asyncpg
from datetime import datetime, date
from decimal import Decimal


# ─────────────────────────────────────────────
# SHARED POOL
# ─────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Return the singleton asyncpg connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        dsn = os.getenv(
            "DATABASE_URL",
            "postgresql://user:pass@localhost:5432/bytetobite",
        )
        if dsn.startswith("postgres://"):
            dsn = "postgresql://" + dsn[len("postgres://"):]

        parsed = urllib.parse.urlparse(dsn)
        query_params = urllib.parse.parse_qs(parsed.query)

        # Check if SSL is requested or needed for remote host
        need_ssl = False
        if "sslmode" in query_params:
            mode = query_params.pop("sslmode", ["require"])[0]
            if mode in ("require", "verify-ca", "verify-full"):
                need_ssl = True
        elif parsed.hostname and parsed.hostname not in ("localhost", "127.0.0.1", "db"):
            need_ssl = True

        # Reconstruct clean DSN without unsupported query parameters
        clean_query = urllib.parse.urlencode({k: v[0] for k, v in query_params.items()})
        clean_dsn = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            clean_query,
            parsed.fragment,
        ))

        pool_kwargs = {
            "dsn": clean_dsn,
            "min_size": 2,
            "max_size": 10,
            "command_timeout": 30,
            "server_settings": {
                "application_name": "bytetobite_api",
                "jit": "off",
            },
        }
        if need_ssl:
            pool_kwargs["ssl"] = "require"

        _pool = await asyncpg.create_pool(**pool_kwargs)
    return _pool


async def close_pool() -> None:
    """Close the pool on app shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ─────────────────────────────────────────────
# QUERY HELPERS
# ─────────────────────────────────────────────
async def fetch(query: str, *args) -> list[dict]:
    """Run a SELECT and return all rows as list[dict]."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def fetchrow(query: str, *args) -> Optional[dict]:
    """Run a SELECT and return the first row, or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def fetchval(query: str, *args) -> Any:
    """Run a SELECT and return a single scalar value."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args) -> str:
    """Run INSERT / UPDATE / DELETE. Returns the command tag."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


# ─────────────────────────────────────────────
# JSON SERIALIZER
# ─────────────────────────────────────────────
def serialize_row(row: dict) -> dict:
    """Convert Postgres types (datetime, Decimal, geography, bytes)
    into JSON-safe Python primitives so FastAPI can return them."""
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, datetime):
            # Frontend expects ms-since-epoch for most timestamps.
            out[k] = int(v.timestamp() * 1000)
        elif isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, bytes):
            out[k] = v.hex()
        elif hasattr(v, "isoformat"):
            # Catch-all for other datetime-like objects.
            out[k] = v.isoformat()
        elif isinstance(v, (list, dict, str, int, float, bool)):
            out[k] = v
        else:
            # Last-resort stringification (e.g. custom Postgres types).
            out[k] = str(v)
    return out