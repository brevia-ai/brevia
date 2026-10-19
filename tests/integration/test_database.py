"""Migrations, start-up checks and recorded runs on a real PostgreSQL database."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from sqlalchemy import column, inspect, make_url, select, table, text, update

from brevia import Unavailable
from brevia.db import migrate
from brevia.db.engine import sync_engine
from brevia.db.store import SqlStore
from brevia.db.tables import SCHEMA, model_calls, runs
from brevia.models import pydantic_ai as adapter_module
from integration.support import MODEL, Answer, answering_brevia, settings_for

pytestmark = pytest.mark.integration

TABLES = {
    "runs",
    "model_calls",
    "configurations",
    "prompts",
    "prompt_revisions",
    "trace_contents",
    "feedback",
}


def tables_in(url: str, schema: str) -> set[str]:
    engine = sync_engine(url)
    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names(schema=schema))
    finally:
        engine.dispose()


def test_migrations_upgrade_and_downgrade_only_in_their_schema(
    database_url: str, schema: str
) -> None:
    public_before = tables_in(database_url, "public")
    migrate.upgrade(database_url, schema)
    assert tables_in(database_url, schema) == TABLES | {"alembic_version"}
    assert tables_in(database_url, "public") == public_before
    assert migrate.database_revision(database_url, schema) == migrate.head()
    migrate.downgrade(database_url, schema, "base")
    assert tables_in(database_url, schema) == {"alembic_version"}
    assert migrate.database_revision(database_url, schema) is None
    migrate.upgrade(database_url, schema)
    assert tables_in(database_url, schema) == TABLES | {"alembic_version"}


async def test_start_refuses_a_schema_that_is_not_migrated(
    database_url: str, schema: str
) -> None:
    store = SqlStore(settings_for(database_url, schema))
    with pytest.raises(Unavailable, match="brevia db upgrade") as raised:
        await store.start()
    assert raised.value.details == {
        "schema": schema,
        "revision": None,
        "expected": migrate.head(),
    }
    migrate.upgrade(database_url, schema)
    engine = sync_engine(database_url)
    try:
        with engine.begin() as connection:
            version = table("alembic_version", column("version_num"), schema=schema)
            connection.execute(update(version).values(version_num="9999"))
    finally:
        engine.dispose()
    with pytest.raises(Unavailable) as raised:
        await store.start()
    assert raised.value.details["revision"] == "9999"


async def test_start_reports_an_unreachable_database_without_its_url() -> None:
    password = "-".join(["pw", "secret"])
    url = f"postgresql://brevia:{password}@127.0.0.1:1/brevia"
    with pytest.raises(Unavailable) as raised:
        await SqlStore(settings_for(url, "brevia")).start()
    assert raised.value.details["operation"] == "start"
    assert password not in str(raised.value.to_dict())
    # The driver error, whose message names host and user, is not reachable.
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


async def test_direct_run_is_recorded_without_holding_connections(
    database_url: str, schema: str, tmp_path: Path
) -> None:
    migrate.upgrade(database_url, schema)
    app = answering_brevia(tmp_path, settings_for(database_url, schema))
    in_use: list[int] = []

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(0.2)  # a slow model
        in_use.append(store.engine.pool.checkedout())  # type: ignore[attr-defined]
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"answer": "Yes."})],
            usage=RequestUsage(input_tokens=100, output_tokens=10),
        )

    store = app._store
    assert isinstance(store, SqlStore)
    async with app:
        with patch.object(
            adapter_module, "_resolve_model", return_value=FunctionModel(respond)
        ):
            result = await app.run("test.answer", {"text": "Is it recorded?"})
        engine = store.engine
        assert engine.pool.checkedout() == 0  # type: ignore[attr-defined]
    assert result == Answer(answer="Yes.")
    assert in_use == [0]
    with pytest.raises(RuntimeError, match="not started"):
        _ = store.engine

    reader = sync_engine(database_url)
    try:
        with reader.connect() as connection:
            connection = connection.execution_options(
                schema_translate_map={SCHEMA: schema}
            )
            (run,) = connection.execute(select(runs)).mappings().all()
            calls = connection.execute(select(model_calls)).mappings().all()
    finally:
        reader.dispose()
    assert run["status"] == "succeeded"
    assert run["mode"] == "direct"
    assert run["input"] == {"text": "Is it recorded?"}
    assert run["result"] == {"answer": "Yes."}
    assert run["error"] is None
    assert run["snapshot"]["activity"] == {"name": "test.answer", "version": "1"}
    assert run["usage"]["requests"] == 1
    assert run["finished_at"] >= run["started_at"]
    (call,) = calls
    assert call["run_id"] == run["id"]
    assert call["sequence"] == 0
    assert call["model"] == MODEL
    assert call["adapter"] == "pydantic-ai"
    assert call["options"] == {
        "reasoning": None,
        "temperature": None,
        "max_tokens": None,
    }
    assert call["input_tokens"] == 100
    assert str(call["cost_usd"]) == "0.00012"
    assert call["prices"] == {
        "input": "1",
        "output": "2",
        "cached_input": None,
        "cache_write": None,
    }


def test_command_line_upgrades_and_reports_the_revision(
    database_url: str, schema: str, jobs_schema: str, tmp_path: Path
) -> None:
    env = {
        **os.environ,
        "BREVIA_DATABASE_URL": database_url,
        "BREVIA_DATABASE_SCHEMA": schema,
        "BREVIA_JOBS_SCHEMA": jobs_schema,
    }

    def brevia(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603  (fixed arguments)
            [sys.executable, "-m", "brevia.cli", *args],
            env=env,
            cwd=tmp_path,  # no .env here
            capture_output=True,
            text=True,
            check=False,
        )

    before = brevia("db", "current")
    assert before.returncode == 1
    assert "revision none" in before.stdout
    upgraded = brevia("db", "upgrade")
    assert upgraded.returncode == 0
    assert f"Jobs schema {jobs_schema} migrated" in upgraded.stdout
    assert "workflow_status" in tables_in(database_url, jobs_schema)
    after = brevia("db", "current")
    assert after.returncode == 0
    assert f"revision {migrate.head()}, expected {migrate.head()}" in after.stdout
    engine = sync_engine(database_url)
    try:
        with engine.begin() as connection:
            version = table("alembic_version", column("version_num"), schema=schema)
            connection.execute(update(version).values(version_num="9999"))
    finally:
        engine.dispose()
    unknown = brevia("db", "upgrade")
    assert unknown.returncode == 1
    assert "migration failed" in unknown.stderr
    assert "Traceback" not in unknown.stderr


def test_upgrade_works_for_a_role_that_owns_only_its_schema(
    database_url: str, schema: str
) -> None:
    role = f"{schema}_owner"
    password = uuid.uuid4().hex
    admin = sync_engine(database_url)
    try:
        with admin.begin() as connection:
            # Names are generated by the test; the password is a literal of the DDL.
            connection.execute(
                text(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{password}'")
            )
            connection.execute(text(f'CREATE SCHEMA "{schema}" AUTHORIZATION "{role}"'))
        url = make_url(database_url).set(username=role, password=password)
        migrate.upgrade(url.render_as_string(hide_password=False), schema)
        assert tables_in(database_url, schema) == TABLES | {"alembic_version"}
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()
