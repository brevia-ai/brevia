"""Fixtures for tests on a real PostgreSQL database.

The database is given by ``BREVIA_TEST_DATABASE_URL``; without it the tests are
skipped. Each test works in its own schema, created by the test and dropped at the end,
so that tests never touch the ``brevia`` schema or ``public``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from brevia import BreviaSettings
from brevia.db.engine import sync_engine


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("BREVIA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("BREVIA_TEST_DATABASE_URL is not set")
    return BreviaSettings(  # normalises the driver
        _env_file=None,  # type: ignore[call-arg]
        database_url=SecretStr(url),
    ).database_url.get_secret_value()


@pytest.fixture
def schema(database_url: str) -> Iterator[str]:
    name = f"brevia_test_{uuid.uuid4().hex[:12]}"
    yield name
    engine = sync_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
    finally:
        engine.dispose()


@pytest.fixture
def jobs_schema(database_url: str) -> Iterator[str]:
    name = f"dbos_test_{uuid.uuid4().hex[:12]}"
    yield name
    engine = sync_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
    finally:
        engine.dispose()
