"""Migrations of the Brevia schema with Alembic.

Migrations are an explicit step of a release (``brevia db upgrade``), run before the
processes start; :class:`~brevia.db.store.SqlStore` only checks the revision.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from dbos import DBOS
from sqlalchemy import Connection

from brevia.db.engine import sync_engine


def _config(connection: Connection | None = None, schema: str = "") -> Config:
    config = Config()
    config.set_main_option("script_location", "brevia.db:migrations")
    config.attributes["connection"] = connection
    config.attributes["schema"] = schema
    return config


def head() -> str | None:
    """Revision the code expects: the last migration."""
    return ScriptDirectory.from_config(_config()).get_current_head()


def current(connection: Connection, schema: str) -> str | None:
    """Revision of the database, or ``None`` when the schema is not migrated."""
    context = MigrationContext.configure(
        connection, opts={"version_table_schema": schema}
    )
    return context.get_current_revision()


def _run(url: str, schema: str, operation: str, revision: str) -> None:
    engine = sync_engine(url)
    try:
        with engine.begin() as connection:
            config = _config(connection, schema)
            if operation == "upgrade":
                command.upgrade(config, revision)
            else:
                command.downgrade(config, revision)
    finally:
        engine.dispose()


def upgrade(url: str, schema: str, revision: str = "head") -> None:
    """Migrate the schema up to ``revision``, creating the schema when missing."""
    _run(url, schema, "upgrade", revision)


def downgrade(url: str, schema: str, revision: str) -> None:
    """Migrate the schema down to ``revision``.

    ``"base"`` removes the tables of the migrations; the schema and the empty Alembic
    version table remain.
    """
    _run(url, schema, "downgrade", revision)


def database_revision(url: str, schema: str) -> str | None:
    """Revision of the database at ``url``."""
    engine = sync_engine(url)
    try:
        with engine.connect() as connection:
            return current(connection, schema)
    finally:
        engine.dispose()


def upgrade_jobs(url: str, schema: str) -> None:
    """Create or migrate the schema of the durable state of jobs (DBOS tables).

    Processes never migrate it: workers start with migrations disabled.
    """
    DBOS.migrate(url, schema=schema)
