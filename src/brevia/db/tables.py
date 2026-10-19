"""Tables of the ``brevia`` schema (specification §8).

Tables are declared in the placeholder schema :data:`SCHEMA`; the engine translates it
to the configured schema, so that no query depends on ``search_path`` or on ``public``.
The migrations create the same tables in the configured schema.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

SCHEMA = "brevia"
"""Placeholder schema of the table definitions, translated to the configured one."""

metadata = MetaData(schema=SCHEMA)

runs = Table(
    "runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("caller", Text, nullable=True),
    Column("end_user", Text, nullable=True),
    Column("activity", Text, nullable=False),
    Column("activity_version", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("input", JSONB, nullable=False),
    # Jobs: overrides as recorded, resolved again by the worker.
    Column("overrides", JSONB, nullable=True),
    # None while a job is queued: its values are resolved when it starts.
    Column("snapshot", JSONB, nullable=True),
    Column("result", JSONB, nullable=True),
    Column("error", JSONB, nullable=True),
    Column("usage", JSONB, nullable=True),
    Column("idempotency_key", Text, nullable=True),
    Column("fingerprint", Text, nullable=True),
    Column(
        "retry_of_run_id",
        Uuid,
        ForeignKey(f"{SCHEMA}.runs.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("deadline_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    CheckConstraint("mode IN ('direct', 'job')", name="runs_mode"),
    CheckConstraint(
        "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
        name="runs_status",
    ),
    Index("runs_status_created_at", "status", "created_at"),
    Index("runs_activity_created_at", "activity", "created_at"),
    Index(
        "runs_idempotency",
        "caller",
        "activity",
        "idempotency_key",
        unique=True,
        postgresql_where=text("idempotency_key IS NOT NULL"),
        postgresql_nulls_not_distinct=True,
    ),
)

model_calls = Table(
    "model_calls",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "run_id",
        Uuid,
        ForeignKey(f"{SCHEMA}.runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("sequence", Integer, nullable=False),
    Column("model", Text, nullable=False),
    Column("adapter", Text, nullable=False),
    Column("adapter_version", Text, nullable=False),
    Column("options", JSONB, nullable=False),
    Column("request_records", JSONB, nullable=False),
    Column("requests", Integer, nullable=False),
    Column("tool_calls", Integer, nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("cache_read_tokens", Integer, nullable=False),
    Column("cache_write_tokens", Integer, nullable=False),
    Column("cost_usd", Numeric, nullable=True),
    Column("prices", JSONB, nullable=True),
    Column("seconds", Double, nullable=False),
    Column("error", Text, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("run_id", "sequence", name="model_calls_run_sequence"),
    Index("model_calls_model_started_at", "model", "started_at"),
)

configurations = Table(
    "configurations",
    metadata,
    Column("activity", Text, primary_key=True),
    Column("values", JSONB, nullable=False),
    Column("version", Integer, nullable=False),
    Column("updated_by", Text, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

prompts = Table(
    "prompts",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("activity", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("text", Text, nullable=True),
    Column("version", Integer, nullable=False),
    Column("updated_by", Text, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("activity", "name", name="prompts_activity_name"),
)

prompt_revisions = Table(
    "prompt_revisions",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "prompt_id",
        BigInteger,
        ForeignKey(f"{SCHEMA}.prompts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("version", Integer, nullable=False),
    Column("operation", Text, nullable=False),
    Column("text", Text, nullable=True),
    Column("sha256", Text, nullable=True),
    Column("author", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "operation IN ('customize', 'reset')", name="prompt_revisions_operation"
    ),
    UniqueConstraint("prompt_id", "version", name="prompt_revisions_prompt_version"),
)

trace_contents = Table(
    "trace_contents",
    metadata,
    # One row per model call whose contents were captured.
    Column(
        "call_id",
        BigInteger,
        ForeignKey(f"{SCHEMA}.model_calls.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # Cleared, with the output, when the contents expire; the row records the
    # deletion (deleted_at). No expiry (expires_at NULL) with retention_days 0.
    Column("instructions", Text, nullable=True),
    Column("user_text", Text, nullable=True),
    Column("output", JSONB, nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    # Only the contents not yet cleared, the ones the cleanup looks for.
    Index(
        "trace_contents_expires_at",
        "expires_at",
        postgresql_where=text("deleted_at IS NULL"),
    ),
)

feedback = Table(
    "feedback",
    metadata,
    # Only inserted: a later feedback adds to the earlier ones, it never replaces them.
    Column("id", Uuid, primary_key=True),
    Column(
        "run_id",
        Uuid,
        ForeignKey(f"{SCHEMA}.runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("kind", Text, nullable=False),
    # Who gave it: the end user of an application, a reviewer or an automatic check.
    Column("source", Text, nullable=False),
    # Corrections: [{target, original, corrected}]; empty for a rating.
    Column("items", JSONB, nullable=False),
    Column("rating", Text, nullable=True),
    Column("comment", Text, nullable=True),
    # Opaque reference to the document of the consumer, such as {system, object_id}.
    Column("external_ref", JSONB, nullable=True),
    Column("caller", Text, nullable=True),
    Column("end_user", Text, nullable=True),
    Column("idempotency_key", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("kind IN ('correction', 'rating')", name="feedback_kind"),
    CheckConstraint(
        "source IN ('user', 'reviewer', 'automatic')", name="feedback_source"
    ),
    CheckConstraint("rating IN ('good', 'bad')", name="feedback_rating"),
    Index("feedback_run_id_created_at", "run_id", "created_at"),
    # A repeated submission with the same key finds the feedback already recorded.
    Index(
        "feedback_idempotency",
        "caller",
        "run_id",
        "idempotency_key",
        unique=True,
        postgresql_where=text("idempotency_key IS NOT NULL"),
        postgresql_nulls_not_distinct=True,
    ),
)
