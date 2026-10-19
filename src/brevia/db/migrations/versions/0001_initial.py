"""Initial schema: runs, model calls, customisations, prompt history, call contents.

Until the first release this migration is edited in place instead of being followed
by new ones (CONTRIBUTING.md, "Database migrations").

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = op.get_context().version_table_schema
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("caller", sa.Text, nullable=True),
        sa.Column("end_user", sa.Text, nullable=True),
        sa.Column("activity", sa.Text, nullable=False),
        sa.Column("activity_version", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("input", JSONB, nullable=False),
        sa.Column("overrides", JSONB, nullable=True),
        sa.Column("snapshot", JSONB, nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("usage", JSONB, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column("fingerprint", sa.Text, nullable=True),
        sa.Column(
            "retry_of_run_id",
            sa.Uuid,
            sa.ForeignKey(f"{schema}.runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('direct', 'job')", name="runs_mode"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="runs_status",
        ),
        schema=schema,
    )
    op.create_index(
        "runs_status_created_at", "runs", ["status", "created_at"], schema=schema
    )
    op.create_index(
        "runs_activity_created_at", "runs", ["activity", "created_at"], schema=schema
    )
    op.create_index(
        "runs_idempotency",
        "runs",
        ["caller", "activity", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_nulls_not_distinct=True,
        schema=schema,
    )
    op.create_table(
        "model_calls",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid,
            sa.ForeignKey(f"{schema}.runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("adapter", sa.Text, nullable=False),
        sa.Column("adapter_version", sa.Text, nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("request_records", JSONB, nullable=False),
        sa.Column("requests", sa.Integer, nullable=False),
        sa.Column("tool_calls", sa.Integer, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Numeric, nullable=True),
        sa.Column("prices", JSONB, nullable=True),
        sa.Column("seconds", sa.Double, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="model_calls_run_sequence"),
        schema=schema,
    )
    op.create_index(
        "model_calls_model_started_at",
        "model_calls",
        ["model", "started_at"],
        schema=schema,
    )

    _create_customizations(schema)
    _create_trace_contents(schema)
    _create_feedback(schema)


def _create_customizations(schema: str | None) -> None:
    op.create_table(
        "configurations",
        sa.Column("activity", sa.Text, primary_key=True),
        sa.Column("values", JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema=schema,
    )
    op.create_table(
        "prompts",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("activity", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("activity", "name", name="prompts_activity_name"),
        schema=schema,
    )
    op.create_table(
        "prompt_revisions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "prompt_id",
            sa.BigInteger,
            sa.ForeignKey(f"{schema}.prompts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("sha256", sa.Text, nullable=True),
        sa.Column("author", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('customize', 'reset')", name="prompt_revisions_operation"
        ),
        sa.UniqueConstraint(
            "prompt_id", "version", name="prompt_revisions_prompt_version"
        ),
        schema=schema,
    )


def _create_trace_contents(schema: str | None) -> None:
    op.create_table(
        "trace_contents",
        sa.Column(
            "call_id",
            sa.BigInteger,
            sa.ForeignKey(f"{schema}.model_calls.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("instructions", sa.Text, nullable=True),
        sa.Column("user_text", sa.Text, nullable=True),
        sa.Column("output", JSONB, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.create_index(
        "trace_contents_expires_at",
        "trace_contents",
        ["expires_at"],
        schema=schema,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def _create_feedback(schema: str | None) -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid,
            sa.ForeignKey(f"{schema}.runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("items", JSONB, nullable=False),
        sa.Column("rating", sa.Text, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("external_ref", JSONB, nullable=True),
        sa.Column("caller", sa.Text, nullable=True),
        sa.Column("end_user", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('correction', 'rating')", name="feedback_kind"),
        sa.CheckConstraint(
            "source IN ('user', 'reviewer', 'automatic')", name="feedback_source"
        ),
        sa.CheckConstraint("rating IN ('good', 'bad')", name="feedback_rating"),
        schema=schema,
    )
    op.create_index(
        "feedback_run_id_created_at",
        "feedback",
        ["run_id", "created_at"],
        schema=schema,
    )
    op.create_index(
        "feedback_idempotency",
        "feedback",
        ["caller", "run_id", "idempotency_key"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    schema = op.get_context().version_table_schema
    for name in (
        "feedback",
        "trace_contents",
        "prompt_revisions",
        "prompts",
        "configurations",
        "model_calls",
        "runs",
    ):
        op.drop_table(name, schema=schema)
