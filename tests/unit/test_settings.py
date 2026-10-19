"""Installation settings of the database and the command line without a database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import answers, simulated
from memory_store import MemoryStore
from pydantic import ValidationError
from summary_example import PROJECT

from brevia import AccessPolicy, Brevia, BreviaSettings
from brevia.cli import main
from brevia.db.store import SqlStore

pytestmark = pytest.mark.unit

PASSWORD = "-".join(["pw", "secret"])
URL = f"postgresql://brevia:{PASSWORD}@localhost:5435/brevia"


def settings(**values: Any) -> BreviaSettings:
    """Settings from ``values`` only, ignoring the environment and ``.env``."""
    return BreviaSettings(_env_file=None, **values)  # type: ignore[call-arg]


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREVIA_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        settings()


def test_database_url_uses_psycopg_and_stays_secret() -> None:
    plain = settings(database_url=URL)
    assert plain.database_url.get_secret_value().startswith("postgresql+psycopg://")
    explicit = settings(database_url=URL.replace("postgresql", "postgresql+psycopg"))
    assert explicit.database_url == plain.database_url
    assert PASSWORD not in repr(plain)
    assert PASSWORD not in str(plain.model_dump())


@pytest.mark.parametrize(
    "url",
    [
        f"mysql://brevia:{PASSWORD}@localhost/brevia",
        f"postgresql+asyncpg://brevia:{PASSWORD}@localhost/brevia",
        "localhost:5432",
        f"postgresql://brevia:{PASSWORD}@localhost:port/brevia",
    ],
)
def test_other_databases_are_refused_without_showing_the_url(url: str) -> None:
    with pytest.raises(ValidationError) as raised:
        settings(database_url=url)
    assert PASSWORD not in str(raised.value)


@pytest.mark.parametrize(
    "schema",
    [
        "Brevia",
        "brevia-next",
        "1brevia",
        'b"; drop',
        "",
        "public",
        "information_schema",
        "pg_brevia",
    ],
)
def test_schema_must_be_a_plain_identifier(schema: str) -> None:
    with pytest.raises(ValidationError, match="database_schema"):
        settings(database_url=URL, database_schema=schema)


def test_from_settings_does_not_contact_the_database(tmp_path: Path) -> None:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    app = Brevia.from_settings(
        settings(database_url=URL, project_file=tmp_path / "brevia.toml")
    )
    assert isinstance(app._store, SqlStore)
    with pytest.raises(RuntimeError, match="not started"):
        _ = app._store.engine


def test_the_access_policy_comes_from_the_settings(tmp_path: Path) -> None:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    project = tmp_path / "brevia.toml"
    default = Brevia.from_settings(settings(database_url=URL, project_file=project))
    assert default.access == AccessPolicy()  # per-caller, no administrators
    app = Brevia.from_settings(
        settings(
            database_url=URL,
            project_file=project,
            access_policy="shared",
            access_admins="ops, admin",
        )
    )
    assert app.access == AccessPolicy(shared=True, admins=frozenset({"ops", "admin"}))
    with pytest.raises(ValidationError, match="access_policy"):
        settings(database_url=URL, access_policy="open")


async def test_snapshot_holds_no_database_settings(
    brevia: Brevia, store: MemoryStore
) -> None:
    with simulated(answers({"summary": "Short."})):
        await brevia.run("document.summarize", {"text": "x"})
    (run,) = store.runs.values()
    assert "postgresql" not in str(run.snapshot)
    assert "database" not in str(run.snapshot)


def test_command_line_reports_invalid_settings_without_the_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("BREVIA_DATABASE_URL", f"mysql://brevia:{PASSWORD}@db/brevia")
    assert main(["db", "current"]) == 2
    error = capsys.readouterr().err
    assert "database_url" in error
    assert PASSWORD not in error


def test_database_url_keeps_an_encoded_password() -> None:
    url = "postgresql://brevia:p%40ss@localhost:5435/brevia"
    value = settings(database_url=url).database_url.get_secret_value()
    assert value == url.replace("postgresql", "postgresql+psycopg")
