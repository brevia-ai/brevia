"""Installation settings, read from the environment and from an optional ``.env`` file.

Settings that differ between installations of the same project live here: the path of
the project file, the database connection and the logging options. The database URL is
a secret: it never appears in snapshots, logs or representations of the settings.
Provider credentials are not Brevia settings:
the model providers read them from their standard variables (for example
``OPENAI_API_KEY`` and ``ANTHROPIC_API_KEY``), so they never pass through project files,
snapshots or logs.
"""

from __future__ import annotations

import re
import socket
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

_SCHEMA = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_RESERVED_SCHEMAS = frozenset({"public", "information_schema"})
_DRIVERS = frozenset({"postgresql", "postgresql+psycopg"})


class BreviaSettings(BaseSettings):
    """Settings of a Brevia installation.

    Each field is read from the environment variable with the ``BREVIA_`` prefix, for
    example ``BREVIA_PROJECT_FILE``.
    """

    # Validation errors never show the input: the database URL may hold a password.
    model_config = SettingsConfigDict(
        env_prefix="BREVIA_",
        env_file=".env",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    project_file: Path = Field(
        default=Path("brevia.toml"),
        description="Project file with declared models, run limits and activity "
        "defaults. Relative paths are resolved from the working directory.",
    )
    fake_models: bool = Field(
        default=False,
        description="Answer every model call with a fake generated from the output "
        "schema, without calling any provider: for local runs and tests, never in "
        "production. Runs record ``fake`` as their model adapter.",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = Field(
        default="text",
        description="Readable text in development, structured JSON in production.",
    )
    database_url: SecretStr = Field(
        description="PostgreSQL connection URL, for example "
        "``postgresql://user:password@host:5432/brevia``. Required. The psycopg driver "
        "is used whether or not the URL names it.",
    )
    database_schema: str = Field(
        default="brevia",
        description="Schema that holds the Brevia tables, created by the migrations. "
        "Lowercase letters, digits and underscores.",
    )
    database_pool_size: int = Field(
        default=5, ge=1, description="Connections kept open by each process."
    )
    database_max_overflow: int = Field(
        default=5,
        ge=0,
        description="Connections opened beyond the pool size under load.",
    )
    database_pool_timeout: float = Field(
        default=30, gt=0, description="Seconds to wait for a free connection."
    )
    database_statement_timeout: float = Field(
        default=30, gt=0, description="Seconds after which a statement is cancelled."
    )
    record_direct_runs: bool = Field(
        default=True,
        description="Record each direct run, its outcome and its model calls.",
    )
    jobs_schema: str = Field(
        default="dbos",
        description="Schema that holds the durable state of jobs, created by "
        "``brevia db upgrade``. Different from the Brevia schema.",
    )
    app_version: str | None = Field(
        default=None,
        max_length=100,
        description="Version of the application, recorded in run snapshots. A job "
        "interrupted under a version starts again only on a worker of the same "
        "version; without it, workers use the version of Brevia "
        "(``brevia-<version>``), which changes when Brevia is updated.",
    )
    worker_id: str = Field(
        default_factory=socket.gethostname,
        min_length=1,
        max_length=100,
        description="Stable identifier of a job worker, the host name by default: "
        "after a restart, a worker starts again the jobs it was running. Two running "
        "workers must never share it, or each would start again the jobs of the "
        "other.",
    )
    worker_concurrency: int = Field(
        default=4, ge=1, description="Jobs a worker runs at the same time."
    )
    files_root: Path | None = Field(
        default=None,
        description="Folder of the files of runs: inputs while a run reads them, "
        "outputs it saves. Without it, runs cannot use files.",
    )
    files_max_bytes: int = Field(
        default=50 * 1024 * 1024, ge=1, description="Largest input file, in bytes."
    )
    files_allowed_extensions: str = Field(
        default=".pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json",
        description="Comma-separated extensions of the input files accepted.",
    )
    files_retention_days: int = Field(
        default=30,
        ge=0,
        description="Days the outputs of a run are kept after the last one it saved; "
        "removed by the daily cleanup. ``0`` keeps them without limit.",
    )
    files_allowed_hosts: str = Field(
        default="",
        description="Comma-separated host names input files may be downloaded from, "
        "with https; empty allows no download.",
    )
    access_policy: Literal["per-caller", "shared"] = Field(
        default="per-caller",
        description="``per-caller``: each caller sees only its own runs; "
        "``shared``: every caller sees everything, as in Brevia 0.15.",
    )
    access_admins: str = Field(
        default="",
        description="Comma-separated names of the callers that see every run and may "
        "change configurations and prompts.",
    )
    worker_shutdown_seconds: int = Field(
        default=30,
        ge=0,
        description="Seconds a stopping worker waits for its running jobs; the jobs "
        "still running start again when it starts again with the same version.",
    )

    @field_validator("database_url")
    @classmethod
    def _postgresql_with_psycopg(cls, url: SecretStr) -> SecretStr:
        # Messages never repeat the URL or the parser error: both may contain the
        # password.
        try:
            parsed = make_url(url.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError("is not a valid database URL") from None
        if parsed.drivername not in _DRIVERS:
            raise ValueError(
                "must be a PostgreSQL URL starting with postgresql:// or "
                "postgresql+psycopg://"
            )
        parsed = parsed.set(drivername="postgresql+psycopg")
        return SecretStr(parsed.render_as_string(hide_password=False))

    @model_validator(mode="after")
    def _separate_schemas(self) -> Self:
        if self.jobs_schema == self.database_schema:
            raise ValueError("jobs_schema must differ from database_schema")
        return self

    @field_validator("database_schema", "jobs_schema")
    @classmethod
    def _plain_identifier(cls, schema: str) -> str:
        if not _SCHEMA.fullmatch(schema):
            raise ValueError(
                "must start with a lowercase letter or underscore and contain only "
                "lowercase letters, digits and underscores (at most 63)"
            )
        if schema in _RESERVED_SCHEMAS or schema.startswith("pg_"):
            raise ValueError(
                "must be a schema of its own, not public, information_schema or pg_*"
            )
        return schema
