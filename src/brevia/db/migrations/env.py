"""Alembic environment of the Brevia schema.

Run through :mod:`brevia.db.migrate`, which passes a connection already in a
transaction and the schema in the configuration attributes: all the migrations of one
command run in that transaction, which PostgreSQL applies or rolls back as a whole.
The schema is created when missing and holds the version table; migrations create
their objects in it and never touch other schemas.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, inspect, text

config = context.config
connection: Connection = config.attributes["connection"]
schema: str = config.attributes["schema"]

# Created only when missing: CREATE SCHEMA IF NOT EXISTS needs the CREATE privilege on
# the database even when the schema exists, which a role that owns only its schema
# lacks. The name is validated by the settings; quoting keeps it an identifier.
if not inspect(connection).has_schema(schema):
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
context.configure(
    connection=connection,
    version_table_schema=schema,
)
with context.begin_transaction():
    context.run_migrations()
