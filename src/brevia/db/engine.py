"""Database engines built from the installation settings.

One asynchronous engine serves each :class:`~brevia.Brevia` instance; migrations use a
synchronous engine without a pool. Both use psycopg on the same URL.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from brevia.config.settings import BreviaSettings
from brevia.db.tables import SCHEMA

CONNECT_TIMEOUT = 10
"""Seconds to wait for a new connection to the server."""

POOL_RECYCLE = 1800
"""Seconds after which a pooled connection is replaced."""


def async_engine(settings: BreviaSettings) -> AsyncEngine:
    """Engine with a bounded pool, a statement timeout and the configured schema.

    Statement parameters are hidden from SQLAlchemy errors: they may hold user data.
    """
    # At least 1 ms: PostgreSQL reads 0 as "no timeout".
    timeout_ms = max(1, round(settings.database_statement_timeout * 1000))
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_recycle=POOL_RECYCLE,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": CONNECT_TIMEOUT,
            "options": f"-c statement_timeout={timeout_ms}",
        },
        execution_options={"schema_translate_map": {SCHEMA: settings.database_schema}},
    )


def sync_engine(url: str) -> Engine:
    """Engine without a pool and without a statement timeout, for migrations."""
    return create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT},
    )
