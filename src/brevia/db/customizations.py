"""Customisations of activities: configuration and prompts, with prompt history.

The functions run inside a transaction of :class:`~brevia.db.store.SqlStore`. Each
change locks its row, so concurrent changes are applied one after the other.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import RowMapping, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from brevia.db.tables import configurations, prompt_revisions, prompts
from brevia.errors import VersionConflict

PromptOperation = Literal["customize", "reset"]


@dataclass(frozen=True)
class StoredConfiguration:
    """Customisation of the configuration of an activity; version 0 when none."""

    values: Mapping[str, Any]
    version: int
    updated_by: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class StoredPrompt:
    """Customisation of a prompt: ``text`` is ``None`` when the file is used."""

    text: str | None
    version: int
    updated_by: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class StoredRevision:
    """One change of a prompt."""

    version: int
    operation: PromptOperation
    text: str | None
    sha256: str | None
    author: str | None
    created_at: datetime


@dataclass(frozen=True)
class Customizations:
    """Customisations of an activity, read together for one run."""

    configuration: StoredConfiguration
    prompts: Mapping[str, StoredPrompt]


NO_CONFIGURATION = StoredConfiguration({}, 0, None, None)
NO_PROMPT = StoredPrompt(None, 0, None, None)

ConfigurationChange = Callable[[Mapping[str, Any]], Mapping[str, Any]]
"""Computes the new customisation from the current one; it may raise to refuse it."""


def check_version(expected: int | None, current: int) -> None:
    """Raise when an expected version is given and is no longer current.

    Raises:
        VersionConflict: ``expected`` is not ``current``.
    """
    if expected is not None and expected != current:
        raise VersionConflict(
            "The customisation was changed meanwhile: read it again",
            {"expected_version": expected, "current_version": current},
        )


def _configuration(row: RowMapping) -> StoredConfiguration:
    return StoredConfiguration(
        values=row["values"],
        version=row["version"],
        updated_by=row["updated_by"],
        updated_at=row["updated_at"],
    )


def _prompt(row: RowMapping) -> StoredPrompt:
    return StoredPrompt(
        text=row["text"],
        version=row["version"],
        updated_by=row["updated_by"],
        updated_at=row["updated_at"],
    )


async def read(connection: AsyncConnection, activity: str) -> Customizations:
    """The customisations of ``activity``; read in one snapshot by the caller."""
    row = (
        (
            await connection.execute(
                select(configurations).where(configurations.c.activity == activity)
            )
        )
        .mappings()
        .first()
    )
    prompt_rows = (
        await connection.execute(select(prompts).where(prompts.c.activity == activity))
    ).mappings()
    return Customizations(
        configuration=NO_CONFIGURATION if row is None else _configuration(row),
        prompts={r["name"]: _prompt(r) for r in prompt_rows},
    )


async def save_configuration(
    connection: AsyncConnection,
    activity: str,
    change: ConfigurationChange,
    *,
    expected_version: int | None,
    author: str | None,
    now: datetime,
) -> StoredConfiguration:
    """Apply ``change`` to the customisation of the configuration of ``activity``."""
    # The row is created empty if missing, then locked: concurrent changes
    # wait for each other and none is lost.
    await connection.execute(
        pg_insert(configurations)
        .values(activity=activity, values={}, version=0, updated_at=now)
        .on_conflict_do_nothing()
    )
    row = (
        (
            await connection.execute(
                select(configurations)
                .where(configurations.c.activity == activity)
                .with_for_update()
            )
        )
        .mappings()
        .one()
    )
    check_version(expected_version, row["version"])
    stored = StoredConfiguration(
        values=dict(change(row["values"])),
        version=row["version"] + 1,
        updated_by=author,
        updated_at=now,
    )
    await connection.execute(
        update(configurations)
        .where(configurations.c.activity == activity)
        .values(
            values=stored.values,
            version=stored.version,
            updated_by=author,
            updated_at=now,
        )
    )
    return stored


async def save_prompt(
    connection: AsyncConnection,
    activity: str,
    name: str,
    text: str | None,
    *,
    operation: PromptOperation,
    sha256: str | None,
    expected_version: int | None,
    author: str | None,
    now: datetime,
) -> StoredPrompt:
    """Save the customisation of a prompt and add a revision."""
    await connection.execute(
        pg_insert(prompts)
        .values(activity=activity, name=name, version=0, updated_at=now)
        .on_conflict_do_nothing()
    )
    row = (
        await connection.execute(
            select(prompts.c.id, prompts.c.version)
            .where(prompts.c.activity == activity, prompts.c.name == name)
            .with_for_update()
        )
    ).one()
    check_version(expected_version, row.version)
    stored = StoredPrompt(text, row.version + 1, author, now)
    await connection.execute(
        update(prompts)
        .where(prompts.c.id == row.id)
        .values(text=text, version=stored.version, updated_by=author, updated_at=now)
    )
    await connection.execute(
        insert(prompt_revisions).values(
            prompt_id=row.id,
            version=stored.version,
            operation=operation,
            text=text,
            sha256=sha256,
            author=author,
            created_at=now,
        )
    )
    return stored


async def prompt_history(
    connection: AsyncConnection, activity: str, name: str
) -> list[StoredRevision]:
    """The revisions of a prompt, the latest first."""
    rows = (
        await connection.execute(
            select(prompt_revisions)
            .join(prompts, prompts.c.id == prompt_revisions.c.prompt_id)
            .where(prompts.c.activity == activity, prompts.c.name == name)
            .order_by(prompt_revisions.c.version.desc())
        )
    ).mappings()
    return [
        StoredRevision(
            version=r["version"],
            operation=r["operation"],
            text=r["text"],
            sha256=r["sha256"],
            author=r["author"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
