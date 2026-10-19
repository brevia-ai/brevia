"""The ``brevia`` command.

Commands::

    brevia db upgrade            migrate the Brevia and jobs schemas to this version
    brevia db current            show the revision of the database and the expected one
    brevia db cleanup            delete expired data (``--dry-run`` only counts it)
    brevia worker MODULE:NAME    run the jobs of the application MODULE.NAME
    brevia token create --user NAME [--minutes 60]
                                 print a token for the caller NAME

The database commands read ``BREVIA_DATABASE_URL``, ``BREVIA_DATABASE_SCHEMA`` and
``BREVIA_JOBS_SCHEMA`` from the environment or ``.env``; only ``cleanup`` reads the
project file, for its retention. The worker imports the application, a
:class:`~brevia.Brevia` object (or a function without arguments that returns it) with
its activities registered, and reads its own settings (``BREVIA_APP_VERSION``,
``BREVIA_WORKER_ID``...) from the same environment. ``token create`` reads only
``BREVIA_TOKENS_SECRET``, and signs the token as ``create_token`` of Brevia 0.15.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import sys
from collections.abc import Sequence
from typing import Any

from alembic.util import CommandError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from brevia.access.auth import AuthSettings, create_token
from brevia.config.settings import BreviaSettings
from brevia.db import migrate
from brevia.errors import BreviaError, cause_types
from brevia.runs.logs import configure_logging


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brevia", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    db = commands.add_parser("db", help="manage the Brevia database schema")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("upgrade", help="migrate the schema to the latest revision")
    db_commands.add_parser("current", help="show the current and expected revisions")
    cleanup = db_commands.add_parser(
        "cleanup", help="delete expired call contents, steps of ended jobs and files"
    )
    cleanup.add_argument(
        "--dry-run", action="store_true", help="count what would be deleted"
    )
    worker = commands.add_parser("worker", help="run the jobs of an application")
    worker.add_argument(
        "application", help="MODULE:NAME of the Brevia application, as importable"
    )
    token = commands.add_parser("token", help="create tokens for callers")
    token_commands = token.add_subparsers(dest="token_command", required=True)
    create = token_commands.add_parser("create", help="print a new token")
    create.add_argument("--user", required=True, help="name of the calling application")
    create.add_argument(
        "--minutes", type=int, default=60, help="validity of the token (default: 60)"
    )
    return parser


def _token(user: str, minutes: int) -> int:
    try:
        secret = AuthSettings().tokens_secret
    except ValidationError as exc:
        print(f"brevia: settings are not valid\n{exc}", file=sys.stderr)
        return 2
    if secret is None or not secret.get_secret_value():
        print("brevia: BREVIA_TOKENS_SECRET is not set", file=sys.stderr)
        return 2
    try:
        print(create_token(user, minutes, secret.get_secret_value()))
    except ValueError as exc:
        print(f"brevia: {exc}", file=sys.stderr)
        return 2
    return 0


async def _cleanup(settings: BreviaSettings, dry_run: bool) -> int:
    from brevia.config.project import load_project
    from brevia.db.store import SqlStore
    from brevia.files.files import FileStore
    from brevia.files.retention import clean
    from brevia.jobs.backend import DbosBackend

    retention = load_project(settings.project_file.resolve()).traces.retention_days
    store, jobs = SqlStore(settings), DbosBackend.from_settings(settings)
    await store.start()
    try:
        await jobs.start()
        try:
            files = FileStore.from_settings(settings)
            cleaned = await clean(store, jobs, retention, dry_run=dry_run, files=files)
        finally:
            await jobs.stop()
    finally:
        await store.stop()
    verb = "would be deleted" if dry_run else "deleted"
    print(
        f"Expired call contents {verb}: {cleaned.contents}; "
        f"recorded steps of ended jobs {verb}: {cleaned.job_steps} "
        f"(retention {f'{retention} days' if retention else 'without limit'}); "
        f"work folders {verb}: "
        f"{cleaned.work_folders}; output folders {verb}: {cleaned.output_folders}"
    )
    if cleaned.files_failed:
        print(
            f"brevia: {cleaned.files_failed} folders of files could not be removed; "
            "see the log",
            file=sys.stderr,
        )
        return 1
    return 0


def _db(command: str, settings: BreviaSettings, dry_run: bool = False) -> int:
    url = settings.database_url.get_secret_value()
    schema = settings.database_schema
    if command == "cleanup":
        try:
            return asyncio.run(_cleanup(settings, dry_run))
        except BreviaError as exc:
            print(f"brevia: cleanup failed: {exc.code}: {exc.message}", file=sys.stderr)
            return 1
    if command == "upgrade":
        migrate.upgrade(url, schema)
        print(f"Schema {schema} at revision {migrate.head()}")
        migrate.upgrade_jobs(url, settings.jobs_schema)
        print(f"Jobs schema {settings.jobs_schema} migrated")
        return 0
    current, expected = migrate.database_revision(url, schema), migrate.head()
    print(f"Schema {schema}: revision {current or 'none'}, expected {expected}")
    return 0 if current == expected else 1


def _application(reference: str) -> Any:
    """The object named by ``MODULE:NAME``, called when it is a function.

    Raises:
        ValueError: The reference is not of the form ``MODULE:NAME``.
    """
    module_name, _, name = reference.partition(":")
    if not module_name or not name:
        raise ValueError("the application must be given as MODULE:NAME")
    # As other servers do, modules of the working directory can be imported.
    if "" not in sys.path:
        sys.path.insert(0, "")
    value = getattr(importlib.import_module(module_name), name)
    return value() if inspect.isfunction(value) else value


def _worker(reference: str, settings: BreviaSettings) -> int:
    from brevia.jobs.worker import serve
    from brevia.runs.application import Brevia

    configure_logging(settings.log_level, settings.log_format)
    try:
        app = _application(reference)
    except (ValueError, ImportError, AttributeError) as exc:
        print(f"brevia: cannot load the application: {exc}", file=sys.stderr)
        return 2
    if not isinstance(app, Brevia):
        print(f"brevia: {reference} is not a Brevia application", file=sys.stderr)
        return 2
    try:
        asyncio.run(serve(app, settings))
    except BreviaError as exc:
        print(f"brevia: worker stopped: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; return the exit status."""
    args = _parser().parse_args(argv)
    if args.command == "token":
        return _token(args.user, args.minutes)
    try:
        # Required settings come from the environment, which mypy cannot see.
        settings = BreviaSettings()  # type: ignore[call-arg]
    except ValidationError as exc:
        # Inputs are hidden by the settings: the message names the fields only.
        print(f"brevia: settings are not valid\n{exc}", file=sys.stderr)
        return 2
    if args.command == "worker":
        return _worker(args.application, settings)
    try:
        return _db(args.db_command, settings, getattr(args, "dry_run", False))
    except SQLAlchemyError as exc:
        # Driver messages may contain the host or the user: only the types are shown.
        causes = " <- ".join(cause_types(exc))
        print(f"brevia: database operation failed ({causes})", file=sys.stderr)
        return 1
    except CommandError as exc:
        # Alembic messages name revisions, not connection details.
        print(f"brevia: migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
