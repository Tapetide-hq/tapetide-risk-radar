"""Read-only database access for the Risk Radar tools.

A single module-level connection pool. Every connection is opened in read-only
mode with a hard statement timeout, so the tools can never mutate data or hang
the agent. Queries are always parameterized.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from psycopg2.pool import ThreadedConnectionPool

load_dotenv()

_pool: ThreadedConnectionPool | None = None


def _statement_timeout_ms() -> int:
    raw = os.getenv("RISK_DB_STATEMENT_TIMEOUT_MS", "15000")
    try:
        return max(1000, int(raw))
    except ValueError:
        return 15000


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set (see .env.example)")
        _pool = ThreadedConnectionPool(minconn=1, maxconn=5, dsn=dsn)
    return _pool


@contextmanager
def cursor() -> Iterator[psycopg2.extras.RealDictCursor]:
    """Yield a RealDictCursor on a read-only, time-bounded connection."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SET statement_timeout = %s", (_statement_timeout_ms(),))
        try:
            yield cur
        finally:
            cur.close()
    finally:
        pool.putconn(conn)


def query(sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    """Run a SELECT and return rows as a list of plain dicts."""
    with cursor() as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
