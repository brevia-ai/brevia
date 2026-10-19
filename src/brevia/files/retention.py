"""Deletion of expired data: contents of model calls, recorded steps of jobs, files.

Internal. The same function serves the daily cleanup run by job workers and the
``brevia db cleanup`` command. Contents expire ``[traces] retention_days`` after the
end of their run; the recorded steps of a job, which hold its input, configuration
and prompts, are deleted that many days after the job ended. With ``0`` both are kept
without a time limit. Records
of runs and model calls (metrics and usage) are kept. Files of runs follow their own
retention (see :meth:`brevia.FileStore.clean`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from brevia.db.store import Store
from brevia.files.files import FileStore
from brevia.jobs.backend import JobBackend
from brevia.jobs.service import engine_ending

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Cleaned:
    """What a cleanup deleted, or would delete with ``dry_run``."""

    contents: int
    job_steps: int
    dry_run: bool
    work_folders: int = 0
    output_folders: int = 0
    files_failed: int = 0


async def clean(
    store: Store,
    jobs: JobBackend | None,
    retention_days: int,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    files: FileStore | None = None,
) -> Cleaned:
    """Delete the data expired at ``now``; with ``dry_run``, only count it.

    Raises:
        Unavailable: The database or the state of jobs cannot be used.
    """
    now = now or datetime.now(UTC)
    contents = await store.clear_expired_contents(now, dry_run=dry_run)
    job_steps = 0
    if jobs is not None and retention_days:

        async def settle(ended: list[tuple[str, str]]) -> None:
            # Only records still active change: the others have their outcome.
            for run_id, status in ended:
                ending = engine_ending(status)
                if ending is not None:
                    recorded, error = ending
                    await store.finish_job(
                        uuid.UUID(run_id), recorded, None, error, now
                    )

        before = now - timedelta(days=retention_days)
        job_steps = await jobs.delete_ended(before, dry_run=dry_run, settle=settle)
    work = outputs = failed = 0
    if files is not None:
        work, outputs, failed = await asyncio.to_thread(
            files.clean, now, dry_run=dry_run
        )
    logger.log(
        logging.WARNING if failed else logging.INFO,
        "Cleanup%s: %d expired call contents, recorded steps of %d ended jobs, "
        "%d work folders, %d output folders, %d folders not removed",
        " (dry run)" if dry_run else "",
        contents,
        job_steps,
        work,
        outputs,
        failed,
    )
    return Cleaned(contents, job_steps, dry_run, work, outputs, failed)
