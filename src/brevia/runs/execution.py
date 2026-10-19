"""Steps shared by direct runs and jobs: resolution, snapshot, execution and records.

Internal: :class:`~brevia.Brevia` is the facade of runs and jobs. A direct run and the
workflow of a job prepare a run each in their own way, then both give it to the same
:class:`Executor`.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python

from brevia.config.configuration import override_paths, resolve
from brevia.config.customization import effective_prompts, stored_customization
from brevia.config.project import ProjectSettings
from brevia.config.prompts import PromptTemplate
from brevia.db.runs import RunOutcome, RunStatus
from brevia.db.store import Store
from brevia.db.values import recordable_json
from brevia.errors import (
    BreviaError,
    InternalError,
    InvalidInput,
    RunTimeout,
    Unavailable,
    cause_types,
    validation_details,
)
from brevia.models import fake
from brevia.models.pydantic_ai import adapter
from brevia.runs.activities import Activity
from brevia.runs.context import SNAPSHOT_FORMAT, RunContext

logger = logging.getLogger(__name__)

LIBRARY = {"name": "brevia", "version": version("brevia")}
"""Library version, recorded in run snapshots (specification §7.2)."""

Prompts = Mapping[str, tuple[PromptTemplate, int | None]]
"""Effective prompts of a run with the version of their customisation, if any."""


def stack_frames(exc: BaseException) -> str:
    """The stack frames of ``exc`` for a log, without its message.

    The frames locate a bug; the message is left out because messages of
    dependencies may contain data or credentials.
    """
    return "".join(traceback.format_tb(exc.__traceback__)).rstrip()


def run_timeout(seconds: float) -> RunTimeout:
    return RunTimeout(
        f"Run exceeded its maximum duration of {seconds} s", {"max_seconds": seconds}
    )


async def resolved(
    store: Store, activity: Activity, overrides: Mapping[str, Any]
) -> tuple[BaseModel, Prompts]:
    """Configuration and prompts of a run, with the customisations read now.

    Raises:
        Unavailable: The customisations cannot be read, or a stored customisation is
            no longer valid for the code.
        InvalidInput: The configuration is not valid.
        OverrideNotAllowed: An override is not on a declared path.
    """
    # Read for every run, never cached: a change applies to the next run.
    custom = await store.customizations(activity.name)
    stored = custom.configuration.values
    if stored:
        stored_customization(activity, stored)
    config = resolve(
        activity.config_type,
        activity.defaults,
        overrides,
        activity.overridable,
        customization=stored,
    )
    return config, effective_prompts(activity, custom.prompts)


def snapshot(
    project: ProjectSettings,
    app_version: str | None,
    activity: Activity,
    config: BaseModel,
    overrides: Mapping[str, Any],
    prompts: Prompts,
) -> dict[str, Any]:
    """Values a run uses, recorded at its start. It contains no secrets.

    The configuration is recorded by alias, the form in which it validates back.
    """
    model = overrides.get("model")
    model_overrides = {"model": model} if isinstance(model, str) else model or {}
    return {
        "format": SNAPSHOT_FORMAT,
        "application": {"version": app_version},
        "activity": {"name": activity.name, "version": activity.version},
        "config": config.model_dump(mode="json", by_alias=True),
        # Overrides as given by a Python caller may hold values without a JSON
        # form, such as Decimal; the model options validate back from JSON.
        "model_overrides": to_jsonable_python(dict(model_overrides)),
        "prompts": {
            name: {
                "text": t.text,
                "source": t.source,
                "sha256": t.sha256,
                "version": version,
            }
            for name, (t, version) in prompts.items()
        },
        "models": {
            reference: info.model_dump(mode="json")
            for reference, info in project.models.items()
        },
        "limits": activity.limits.model_dump(mode="json"),
        "adapter": adapter(),
        "library": dict(LIBRARY),
        "capture": {
            "mode": activity.capture,
            "retention_days": project.traces.retention_days,
        },
    }


def validated_input(
    activity: Activity, request: BaseModel | Mapping[str, Any]
) -> BaseModel:
    """``request`` as an instance of the input schema of the activity.

    Raises:
        InvalidInput: The input is not valid.
    """
    if isinstance(request, activity.input_type):
        return request
    data = (
        request.model_dump(by_alias=True) if isinstance(request, BaseModel) else request
    )
    try:
        return from_record(activity.input_type, data)
    except ValidationError as exc:
        # Not chained: the message of a ValidationError quotes the input values,
        # which a standard traceback would print; the details list the problems.
        raise InvalidInput(
            f"Input of activity {activity.name!r} is not valid",
            validation_details(exc),
        ) from None


MAX_KEY_LENGTH = 200
"""Longest idempotency key of a job or a feedback."""


def check_key(key: str | None) -> None:
    """Refuse an idempotency key that is blank, too long or holds a NUL character,
    which PostgreSQL refuses in text.

    Raises:
        InvalidInput: The key is not valid.
    """
    if key is None:
        return
    if (
        not isinstance(key, str)
        or not key.strip()
        or len(key) > MAX_KEY_LENGTH
        or "\x00" in key
    ):
        raise InvalidInput(
            "The idempotency key must be a non-blank string of at most "
            f"{MAX_KEY_LENGTH} characters, without NUL characters"
        )


def to_record(value: BaseModel) -> Any:
    """``value`` in the JSON form of its record: fields under their aliases, without
    computed fields, which are not part of the input of a schema."""
    return value.model_dump(mode="json", by_alias=True, exclude_computed_fields=True)


def from_record[ModelT: BaseModel](model_type: type[ModelT], data: Any) -> ModelT:
    """An instance of ``model_type`` from ``data``, whose fields may be named by
    their aliases or by their names: the JSON form of a record or of a request.

    Raises:
        ValidationError: ``data`` is not valid for ``model_type``.
    """
    return model_type.model_validate(data, by_alias=True, by_name=True)


def recorded_input(activity: Activity, payload: BaseModel) -> Any:
    """The input as JSON for its record.

    Raises:
        InvalidInput: The input has no finite JSON form.
    """
    try:
        return recordable_json(to_record(payload))
    except ValueError as exc:
        raise InvalidInput(
            f"Input of activity {activity.name!r} cannot be recorded: values "
            "must be finite and have a JSON form",
            {"reason": str(exc)},
        ) from None


def recorded_snapshot(activity: Activity, values: Mapping[str, Any]) -> Any:
    """The snapshot as JSON for its record.

    Raises:
        InvalidInput: The configuration has no finite JSON form.
    """
    try:
        return recordable_json(values)
    except ValueError as exc:
        raise InvalidInput(
            f"Configuration of activity {activity.name!r} cannot be recorded: "
            "values must be finite and have a JSON form",
            {"reason": str(exc)},
        ) from None


def recorded_output(
    activity: Activity, output: BaseModel, *, read_back: bool = False
) -> Any:
    """The output as JSON for its record.

    With ``read_back``, for jobs, whose result is read from the record, the output
    schema must accept it.

    Raises:
        InternalError: The output has no finite JSON form, or, with ``read_back``,
            the output schema does not accept it: the job would end with a result
            that cannot be read.
    """
    try:
        recorded = recordable_json(to_record(output))
    except ValueError as exc:
        raise InternalError(
            f"Output of activity {activity.name!r} cannot be recorded: values "
            "must be finite and have a JSON form",
            {"reason": str(exc)},
        ) from None
    if not read_back:
        return recorded
    try:
        from_record(activity.output_type, recorded)
    except ValidationError as exc:
        raise InternalError(
            f"Output of activity {activity.name!r} cannot be read back from its "
            "record: the output schema must accept its own JSON form",
            validation_details(exc),
        ) from None
    return recorded


def recorded_error(error: Mapping[str, Any]) -> Any:
    """The error of a run as JSON; details without a JSON form are dropped."""
    try:
        return recordable_json(error)
    except ValueError:
        return {
            **recordable_json({k: v for k, v in error.items() if k != "details"}),
            "details": {},
        }


async def execute(
    activity: Activity, payload: BaseModel, ctx: RunContext[Any]
) -> object:
    """Run the activity within the time left to the run.

    The deadline interrupts asynchronous waits. Blocking code that never yields to
    the event loop cannot be interrupted: the elapsed time is checked again when
    the activity returns. The work folder of the input files is removed at the end.
    """
    seconds = ctx._tracker.seconds
    started = time.monotonic()
    try:
        async with asyncio.timeout(seconds) as deadline:
            result = await activity.function(payload, ctx)
    except TimeoutError as exc:
        if deadline.expired():
            raise run_timeout(activity.limits.max_seconds) from exc
        raise
    finally:
        # Inputs are not kept: the work folder goes with the run, however it ends,
        # once the threads that may still use it have ended.
        await ctx.files.close()
    if seconds is not None and time.monotonic() - started > seconds:
        raise run_timeout(activity.limits.max_seconds)
    return result


def checked_output(activity: Activity, result: object) -> BaseModel:
    """``result`` when it is an instance of the output schema.

    Raises:
        InternalError: The activity returned another type.
    """
    if isinstance(result, activity.output_type):
        return result
    raise InternalError(
        f"Activity {activity.name!r} returned {type(result).__name__} instead of "
        f"{activity.output_type.__name__}"
    )


class Executor:
    """Runs prepared activities, direct or as jobs, and records their outcomes.

    Outcome writes are shielded from cancellation and kept until they end;
    :meth:`drain` awaits those under way.
    """

    def __init__(self, store: Store) -> None:
        self._store = store
        self._writes: set[asyncio.Task[None]] = set()

    async def drain(self) -> None:
        """Wait for the outcome writes under way; their failures are not raised."""
        if self._writes:
            await asyncio.gather(*self._writes, return_exceptions=True)

    async def run(
        self,
        activity: Activity,
        payload: BaseModel,
        ctx: RunContext[Any],
        overrides: Mapping[str, Any],
        *,
        record: bool,
        read_back: bool = False,
    ) -> BaseModel:
        """Execute a prepared run, direct or job, and record its outcome and its model
        calls when ``record`` is set. With ``read_back``, for jobs, the recorded output
        must be valid for the output schema (:func:`recorded_output`)."""
        name = activity.name
        extra = {"run_id": ctx.run_id, "activity": name}
        logger.info(
            "Run started: %s version %s, overrides %s",
            name,
            activity.version,
            sorted(override_paths(overrides, activity.config_type)),
            extra=extra,
        )
        started = time.monotonic()
        unexpected: InternalError | None = None
        try:
            returned = await execute(activity, payload, ctx)
            # An activity may have caught the LimitExceeded of a call that went over.
            ctx._tracker.check_totals()
            output = checked_output(activity, returned)
            result = (
                recorded_output(activity, output, read_back=read_back)
                if record
                else None
            )
        except asyncio.CancelledError:
            logger.warning("Run cancelled: %s", name, extra=extra)
            await self.record_cancelled(ctx, record=record)
            raise
        except BreviaError as exc:
            logger.warning(
                "Run failed: %s with %s after %.3f s",
                name,
                exc.code,
                time.monotonic() - started,
                extra=extra,
            )
            # A recording failure replaces the error, which remains its context.
            await self.record(ctx, "failed", error=exc.to_dict(), record=record)
            raise
        except Exception as exc:
            logger.error(
                "Run failed unexpectedly: %s with %s\n%s",
                name,
                type(exc).__name__,
                stack_frames(exc),
                extra=extra,
            )
            unexpected = InternalError(
                f"Activity {name!r} failed unexpectedly: {type(exc).__name__}"
            )
        if unexpected is not None:
            # Recorded and raised outside the handler, so that neither the error nor
            # a recording failure that replaces it carries the original exception as
            # context: a standard traceback of the caller would print its message.
            await self.record(ctx, "failed", error=unexpected.to_dict(), record=record)
            raise unexpected from None
        await self.record(ctx, "succeeded", result=result, record=record)
        usage = ctx.usage
        logger.info(
            "Run succeeded: %s in %.3f s, %d model requests, cost %s",
            name,
            time.monotonic() - started,
            usage["requests"],
            usage["cost_usd"] if usage["cost_usd"] is not None else "unknown",
            extra=extra,
        )
        return output

    async def record(
        self,
        ctx: RunContext[Any],
        status: RunStatus,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        *,
        record: bool = True,
    ) -> None:
        """Record the outcome of a run, unless ``record`` is false.

        The write is shielded: a cancellation that arrives meanwhile does not leave
        the run recorded as running.

        Raises:
            Unavailable: The outcome cannot be recorded.
        """
        if not record:
            return
        outcome = _outcome(ctx, status, result, error)
        try:
            await self._shielded_write(ctx, outcome)
        except Unavailable as exc:
            logger.error(
                "Run outcome not recorded: %s, %s",
                ctx.activity,
                exc.details.get("cause"),
                extra={"run_id": ctx.run_id, "activity": ctx.activity},
            )
            raise

    async def record_cancelled(self, ctx: RunContext[Any], *, record: bool) -> None:
        """Record a cancelled run; a failure is logged and the cancellation goes on."""
        if not record:
            return
        try:
            await self._shielded_write(ctx, _outcome(ctx, "cancelled"))
        except asyncio.CancelledError:
            pass  # cancelled again: the write goes on and reports its own failure
        except Exception as exc:
            logger.warning(
                "Cancelled run not recorded: %s, %s",
                ctx.activity,
                cause_types(exc),
                extra={"run_id": ctx.run_id, "activity": ctx.activity},
            )

    async def _shielded_write(self, ctx: RunContext[Any], outcome: RunOutcome) -> None:
        """Write an outcome in a task that a cancellation of the caller does not stop.

        The task is kept until it ends. If the caller is cancelled meanwhile, a
        failure of the write is logged here, with the types of its causes only.
        """
        task = asyncio.ensure_future(self._store.finish_run(outcome))
        self._writes.add(task)
        orphan = False

        def done(task: asyncio.Task[None]) -> None:
            self._writes.discard(task)
            if task.cancelled():
                return
            exc = task.exception()  # retrieved here, so asyncio does not report it
            if exc is not None and orphan:
                logger.error(
                    "Run outcome not recorded after cancellation: %s, %s",
                    ctx.activity,
                    cause_types(exc),
                    extra={"run_id": ctx.run_id, "activity": ctx.activity},
                )

        task.add_done_callback(done)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            orphan = True
            raise


def _outcome(
    ctx: RunContext[Any],
    status: RunStatus,
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
) -> RunOutcome:
    finished = datetime.now(UTC)
    calls = list(ctx._tracker.usage.calls)
    fake_adapter = dict(fake.ADAPTER)
    return RunOutcome(
        id=uuid.UUID(ctx.run_id),
        status=status,
        result=result,
        error=None if error is None else recorded_error(error),
        usage=ctx.usage,
        calls=calls,
        adapter=fake_adapter
        if any(c.adapter == fake_adapter for c in calls)
        else adapter(),
        finished_at=finished,
        contents_expire_at=(
            finished + timedelta(days=ctx.retention_days)
            if ctx.capture == "full" and ctx.retention_days
            else None
        ),
    )
