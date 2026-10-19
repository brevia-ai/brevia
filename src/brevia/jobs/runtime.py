"""What the job modules use of a :class:`~brevia.Brevia` instance.

The service, the workflow and the worker receive these dependencies explicitly
instead of reading the private attributes of the application, so that a change of
:class:`~brevia.Brevia` that keeps them does not break jobs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from brevia.access.access import AccessPolicy
from brevia.config.project import ProjectSettings
from brevia.db.store import Store
from brevia.files.files import FileStore
from brevia.jobs.backend import JobBackend
from brevia.runs.activities import Activity
from brevia.runs.execution import Executor


@dataclass(frozen=True)
class JobRuntime:
    """Dependencies of jobs, built once by :class:`~brevia.Brevia`.

    Attributes:
        project: Validated project settings.
        store: Store of the records.
        executor: Runs prepared activities and records their outcomes, shared with
            direct runs.
        backend: Durable state of jobs.
        activity: Looks up a registered activity by name; raises
            :class:`~brevia.errors.NotFound` when there is none.
        check_started: Raises ``RuntimeError`` when Brevia is not started.
        access: Which jobs a caller may read and act on.
        files: Where the files of runs are kept; ``None`` without files.
    """

    project: ProjectSettings
    store: Store
    executor: Executor
    backend: JobBackend
    activity: Callable[[str], Activity]
    check_started: Callable[[], None]
    access: AccessPolicy
    files: FileStore | None
