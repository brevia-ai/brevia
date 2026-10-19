"""Public types of jobs: :class:`JobState`, :class:`JobPage` and :class:`RunHandle`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from brevia.access.access import Caller
from brevia.db.jobs import JobStatus

if TYPE_CHECKING:
    from brevia.jobs.service import JobService


@dataclass(frozen=True)
class JobState:
    """A job as recorded.

    Attributes:
        run_id: Identifier of the job.
        activity: Name of the activity.
        activity_version: Version of the activity the job was submitted for.
        status: Status of the job.
        created_at: When the job was accepted.
        started_at: When a worker started it, or ``None`` while it is queued.
        finished_at: When it ended, or ``None``.
        error: ``{code, message, details, retryable}`` of a failed or cancelled job.
        usage: Usage of the model calls of an ended job.
        retry_of: Identifier of the job this one retries, if any.
    """

    run_id: str
    activity: str
    activity_version: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: Mapping[str, Any] | None
    usage: Mapping[str, Any] | None
    retry_of: str | None

    @property
    def done(self) -> bool:
        """Whether the job has ended."""
        return self.status in ("succeeded", "failed", "cancelled")


@dataclass(frozen=True)
class JobPage:
    """A page of jobs, newest first, returned by :meth:`brevia.Brevia.jobs`.

    Attributes:
        jobs: The jobs of the page.
        next_cursor: Pass it as ``cursor``, with the same filters, for the next page;
            ``None`` on the last page.
    """

    jobs: list[JobState]
    next_cursor: str | None


class RunHandle:
    """Handle of a job, returned by :meth:`brevia.Brevia.submit` and
    :meth:`brevia.Brevia.job`. It holds only the identifier and the caller that asked
    for it: every method reads the job again, and a job the caller may not see is not
    found.
    """

    def __init__(
        self, service: JobService, run_id: str, caller: Caller | None = None
    ) -> None:
        self._service = service
        self.run_id = run_id
        self.caller = caller

    def __repr__(self) -> str:
        return f"RunHandle({self.run_id!r})"

    async def status(self) -> JobState:
        """The job as recorded now.

        Raises:
            NotFound: There is no such job, or the caller may not see it.
            Unavailable: The job cannot be read.
        """
        return await self._service.state(self.run_id, self.caller)

    async def result(self, wait: float | None = None) -> BaseModel:
        """Output of the job, waiting for it to end at most ``wait`` seconds.

        Waiting does not change the job: when the time is over, it goes on.

        Raises:
            NotReady: The job has not ended (within ``wait`` seconds).
            BreviaError: The error of a failed job, or ``Cancelled``.
            NotFound: There is no such job, or the caller may not see it.
            Unavailable: The job cannot be read.
        """
        return await self._service.result(self.run_id, wait, self.caller)

    async def cancel(self) -> JobState:
        """Cancel the job, if it has not ended; calling it again does nothing.

        A running job is stopped within about a second, also during a model call;
        the calls made so far are recorded with the job, and effects already
        produced are not undone.

        Raises:
            NotFound: There is no such job, or the caller may not see it.
            Unavailable: The job cannot be cancelled now.
        """
        return await self._service.cancel(self.run_id, self.caller)

    async def retry(self, *, idempotency_key: str | None = None) -> RunHandle:
        """Submit a new job linked to this failed or cancelled one, with the same
        input and overrides; configuration and prompts are read again. The new job
        belongs to the caller of this one, also when an administrator asks.

        Raises:
            Busy: The job has not ended.
            Unsupported: The job succeeded.
            InvalidInput: The input is no longer valid for the activity.
            NotFound: There is no such job, the caller may not see it, or its
                activity is not registered.
            Unavailable: The job cannot be read or submitted.
        """
        return await self._service.retry(self.run_id, idempotency_key, self.caller)

    async def file(self, name: str) -> Path:
        """Path of the output file ``name`` that the job saved, to read it.

        The file belongs to the job: it is found only when the caller may see the
        job. Do not modify it.

        Raises:
            NotFound: There is no such job, the caller may not see it, or the job has
                no output with this name.
            Unavailable: The job cannot be read.
        """
        return await self._service.file(self.run_id, name, self.caller)
