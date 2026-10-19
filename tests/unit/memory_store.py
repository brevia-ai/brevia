"""Store in memory for unit tests: runs, jobs and customisations, without a database."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from brevia.db.customizations import (
    NO_CONFIGURATION,
    NO_PROMPT,
    ConfigurationChange,
    Customizations,
    PromptOperation,
    StoredConfiguration,
    StoredPrompt,
    StoredRevision,
    check_version,
)
from brevia.db.feedback import FeedbackRecord, RunOwner
from brevia.db.jobs import (
    ACTIVE,
    Enqueue,
    JobQuery,
    JobRecord,
    JobStatus,
    NewJob,
)
from brevia.db.runs import NewRun, RunOutcome
from brevia.errors import Unavailable
from brevia.models.limits import CallUsage


@dataclass
class MemoryStore:
    """Keeps runs and outcomes in dictionaries; ``fail`` makes an operation fail.

    JSON fields are checked as PostgreSQL would: values must have a JSON form and be
    finite. ``start_delay`` and ``finish_delay`` slow down the start and the write of
    outcomes, and ``finishing`` is set when one starts. Customisations follow the
    version rules of the database store.
    """

    runs: dict[uuid.UUID, NewRun] = field(default_factory=dict)
    outcomes: dict[uuid.UUID, RunOutcome] = field(default_factory=dict)
    fail: set[str] = field(default_factory=set)
    configurations: dict[str, StoredConfiguration] = field(default_factory=dict)
    prompts: dict[tuple[str, str], StoredPrompt] = field(default_factory=dict)
    revisions: dict[tuple[str, str], list[StoredRevision]] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    start_delay: float = 0
    finish_delay: float = 0
    finishing: asyncio.Event = field(default_factory=asyncio.Event)
    jobs: dict[uuid.UUID, JobRecord] = field(default_factory=dict)
    feedback: list[FeedbackRecord] = field(default_factory=list)

    def _check(self, operation: str) -> None:
        if operation in self.fail:
            raise Unavailable(
                "Database operation failed",
                {"operation": operation, "cause": ["OperationalError"]},
            )

    async def start(self) -> None:
        await asyncio.sleep(self.start_delay)
        self._check("start")
        self.events.append("start")

    async def stop(self) -> None:
        self.events.append("stop")

    async def check(self) -> None:
        self._check("check")

    async def create_run(self, run: NewRun) -> None:
        self._check("create_run")
        json.dumps([run.input, run.snapshot], allow_nan=False)
        assert run.id not in self.runs
        self.runs[run.id] = run

    async def finish_run(self, outcome: RunOutcome) -> None:
        self.finishing.set()
        await asyncio.sleep(self.finish_delay)
        self._check("finish_run")
        json.dumps(
            [outcome.result, outcome.error, outcome.usage, outcome.adapter],
            allow_nan=False,
        )
        job = self.jobs.get(outcome.id)
        if job is None:
            assert outcome.id in self.runs
            assert outcome.id not in self.outcomes
            self.outcomes[outcome.id] = outcome
        elif job.status in ACTIVE:
            if outcome.status == "cancelled":
                return  # a stop of the worker: the job starts again
            self.jobs[outcome.id] = replace(
                job,
                status=outcome.status,
                result=outcome.result,
                error=outcome.error,
                usage=outcome.usage,
                finished_at=outcome.finished_at,
            )
            self.outcomes[outcome.id] = outcome
        elif job.status == "cancelled" and not self._calls_recorded(outcome.id):
            # Cancelled meanwhile: the status stays, the usage and calls are added,
            # unless calls are already recorded (as the database decides).
            self.jobs[outcome.id] = replace(job, usage=outcome.usage)
            self.outcomes[outcome.id] = replace(outcome, status="cancelled")

    def _calls_recorded(self, run_id: uuid.UUID) -> bool:
        recorded = self.outcomes.get(run_id)
        return recorded is not None and bool(recorded.calls)

    def only_outcome(self) -> RunOutcome:
        """The outcome of the single run recorded."""
        (outcome,) = self.outcomes.values()
        return outcome

    def summary(self) -> dict[str, Any]:
        """Number of runs and statuses, for quick assertions."""
        return {
            "runs": len(self.runs),
            "statuses": sorted(o.status for o in self.outcomes.values()),
        }

    async def customizations(self, activity: str) -> Customizations:
        self._check("customizations")
        return Customizations(
            configuration=self.configurations.get(activity, NO_CONFIGURATION),
            prompts={
                name: prompt
                for (owner, name), prompt in self.prompts.items()
                if owner == activity
            },
        )

    async def save_configuration(
        self,
        activity: str,
        change: ConfigurationChange,
        *,
        expected_version: int | None,
        author: str | None,
        now: datetime,
    ) -> StoredConfiguration:
        self._check("save_configuration")
        current = self.configurations.get(activity, NO_CONFIGURATION)
        check_version(expected_version, current.version)
        values = dict(change(current.values))
        json.dumps(values, allow_nan=False)
        stored = StoredConfiguration(values, current.version + 1, author, now)
        self.configurations[activity] = stored
        return stored

    async def save_prompt(
        self,
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
        self._check("save_prompt")
        key = (activity, name)
        current = self.prompts.get(key, NO_PROMPT)
        check_version(expected_version, current.version)
        stored = StoredPrompt(text, current.version + 1, author, now)
        self.prompts[key] = stored
        self.revisions.setdefault(key, []).append(
            StoredRevision(stored.version, operation, text, sha256, author, now)
        )
        return stored

    async def prompt_history(self, activity: str, name: str) -> list[StoredRevision]:
        self._check("prompt_history")
        return list(reversed(self.revisions.get((activity, name), [])))

    async def clear_expired_contents(self, now: datetime, *, dry_run: bool) -> int:
        self._check("clear_expired_contents")
        self.events.append(f"clear_expired_contents dry_run={dry_run}")
        return 0

    # ---------- jobs, with the rules of the database store ----------

    async def submit_job(self, job: NewJob, enqueue: Enqueue) -> tuple[JobRecord, bool]:
        self._check("submit_job")
        json.dumps([job.input, job.overrides], allow_nan=False)
        if job.idempotency_key is not None:
            for existing in self.jobs.values():
                if (existing.caller, existing.activity, existing.idempotency_key) == (
                    job.caller,
                    job.activity,
                    job.idempotency_key,
                ):
                    return existing, False
        record = JobRecord(
            id=job.id,
            activity=job.activity,
            activity_version=job.activity_version,
            status="queued",
            input=job.input,
            overrides=job.overrides,
            snapshot=None,
            result=None,
            error=None,
            usage=None,
            idempotency_key=job.idempotency_key,
            fingerprint=job.fingerprint,
            retry_of_run_id=job.retry_of_run_id,
            created_at=job.created_at,
            started_at=None,
            deadline_at=None,
            finished_at=None,
            caller=job.caller,
            end_user=job.end_user,
        )
        enqueue(None)  # not atomic here: the database store queues in its transaction
        self.jobs[job.id] = record
        return record, True

    async def job(self, run_id: uuid.UUID) -> JobRecord | None:
        self._check("job")
        return self.jobs.get(run_id)

    async def run_owner(self, run_id: uuid.UUID) -> RunOwner | None:
        self._check("run_owner")
        if run_id in self.runs:
            return RunOwner(self.runs[run_id].caller)
        if run_id in self.jobs:
            return RunOwner(self.jobs[run_id].caller)
        return None

    async def add_feedback(self, record: FeedbackRecord) -> tuple[FeedbackRecord, bool]:
        self._check("add_feedback")
        assert record.run_id in self.runs or record.run_id in self.jobs
        json.dumps([record.items, record.external_ref], allow_nan=False)
        if record.idempotency_key is not None:
            for existing in self.feedback:
                if (existing.caller, existing.run_id, existing.idempotency_key) == (
                    record.caller,
                    record.run_id,
                    record.idempotency_key,
                ):
                    return existing, False
        self.feedback.append(record)
        return record, True

    async def list_jobs(self, query: JobQuery) -> list[JobRecord]:
        self._check("list_jobs")
        found = [
            job
            for job in self.jobs.values()
            if (query.owner is None or job.caller == query.owner)
            and query.activity in (None, job.activity)
            and (not query.statuses or job.status in query.statuses)
            and query.idempotency_key in (None, job.idempotency_key)
            and (query.after is None or (job.created_at, job.id) < query.after)
        ]
        found.sort(key=lambda job: (job.created_at, job.id), reverse=True)
        return found[: query.limit]

    async def start_job(
        self,
        run_id: uuid.UUID,
        snapshot: Mapping[str, Any],
        now: datetime,
        deadline: datetime | None,
    ) -> JobRecord | None:
        self._check("start_job")
        record = self.jobs.get(run_id)
        if record is None or record.status not in ACTIVE:
            return None
        json.dumps(snapshot, allow_nan=False)
        record = replace(
            record,
            status="running",
            snapshot=snapshot,
            started_at=record.started_at or now,
            deadline_at=record.deadline_at or deadline,
        )
        self.jobs[run_id] = record
        return record

    async def find_job(
        self, caller: str | None, activity: str, idempotency_key: str
    ) -> JobRecord | None:
        self._check("find_job")
        wanted = (caller, activity, idempotency_key)
        for record in self.jobs.values():
            if (record.caller, record.activity, record.idempotency_key) == wanted:
                return record
        return None

    def calls_of(self, run_id: uuid.UUID) -> list[CallUsage]:
        """Recorded model calls of a run, in sequence order."""
        outcome = self.outcomes.get(run_id)
        return [] if outcome is None else list(outcome.calls)

    async def finish_job(
        self,
        run_id: uuid.UUID,
        status: JobStatus,
        result: Mapping[str, Any] | None,
        error: Mapping[str, Any] | None,
        now: datetime,
    ) -> bool:
        self._check("finish_job")
        json.dumps([result, error], allow_nan=False)
        record = self.jobs[run_id]
        if record.status not in ACTIVE:
            return False
        calls = self.calls_of(run_id)
        unknown = any(c.cost_usd is None for c in calls)
        cost = sum((c.cost_usd for c in calls if c.cost_usd is not None), Decimal(0))
        usage = {
            "requests": sum(c.requests for c in calls),
            "tool_calls": sum(c.tool_calls for c in calls),
            "input_tokens": sum(c.input_tokens for c in calls),
            "output_tokens": sum(c.output_tokens for c in calls),
            "cache_read_tokens": sum(c.cache_read_tokens for c in calls),
            "cache_write_tokens": sum(c.cache_write_tokens for c in calls),
            "cost_usd": None if unknown else str(cost),
            "cost_kind": "unknown" if unknown else "estimate",
        }
        self.jobs[run_id] = replace(
            record,
            status=status,
            result=result,
            error=error,
            usage=usage,
            finished_at=now,
        )
        return True
