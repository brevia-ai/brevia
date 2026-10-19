"""Runs: a direct run answers with its ``run_id``, ``status`` and ``output``; a job
answers at once with its state.

A job is then followed with ``GET /runs/{run_id}``: the request never waits for the
job to end, and the job runs in a worker process. Every endpoint passes the caller of
the request to the operation, so that the access policy decides what it may see.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from brevia.access.access import Caller
from brevia.api.requests import (
    BreviaDep,
    CallerDep,
    EndUser,
    acting_for,
    error_response,
)
from brevia.api.routes.activities import registered
from brevia.db.jobs import JobStatus
from brevia.errors import InvalidInput, NotFound, NotReady
from brevia.jobs.handle import JobState, RunHandle
from brevia.jobs.service import MAX_PAGE
from brevia.runs.application import Brevia
from brevia.runs.feedback import Feedback, FeedbackRequest

router = APIRouter(prefix="/runs", tags=["runs"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]
"""Header of a job submission or of feedback: the same key and request give back the
same job or feedback."""


class RunRequest(BaseModel):
    """A run of an activity."""

    model_config = ConfigDict(extra="forbid")

    activity: str
    input: dict[str, Any]
    overrides: dict[str, Any] | None = None
    mode: Literal["direct", "job"] | None = None
    """Required only when the activity supports both modes."""
    end_user: EndUser = None


class DirectRun(BaseModel):
    """A direct run that succeeded: its identifier, for feedback, and its output."""

    run_id: str
    status: Literal["succeeded"]
    output: Any
    """Any JSON value: an object, or a list or a scalar for a root model."""


class RunState(BaseModel):
    """A job as recorded; see :class:`~brevia.JobState`."""

    run_id: str
    activity: str
    activity_version: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: dict[str, Any] | None
    usage: dict[str, Any] | None
    retry_of: str | None

    @classmethod
    def of(cls, state: JobState) -> RunState:
        return cls(
            run_id=state.run_id,
            activity=state.activity,
            activity_version=state.activity_version,
            status=state.status,
            created_at=state.created_at,
            started_at=state.started_at,
            finished_at=state.finished_at,
            error=None if state.error is None else dict(state.error),
            usage=None if state.usage is None else dict(state.usage),
            retry_of=state.retry_of,
        )


def output_json(output: BaseModel) -> Any:
    """An output as JSON, as ``output_schema`` of its activity describes it."""
    return output.model_dump(mode="json", by_alias=True)


def has_jobs(brevia: Brevia) -> bool:
    """Whether an activity of the application supports jobs."""
    return any("job" in activity.modes for activity in brevia.activities.values())


def job_of(brevia: Brevia, run_id: str, caller: Caller) -> RunHandle:
    """The handle of a job; in an application without jobs, no job is found.

    Raises:
        NotFound: No activity supports jobs, or ``run_id`` is not a job identifier.
    """
    if not has_jobs(brevia):
        raise NotFound("Job not found", {"run_id": run_id})
    return brevia.job(run_id, caller=caller)


class FeedbackBody(FeedbackRequest):
    """Feedback on a run, with the end user the caller acts for."""

    end_user: EndUser = None


class RunPage(BaseModel):
    """A page of jobs, newest first; see :class:`~brevia.JobPage`."""

    jobs: list[RunState]
    next_cursor: str | None


_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such job, or the caller may not see it"},
}


@router.post(
    "",
    status_code=202,
    response_model=RunState,
    responses={
        200: {"description": "A direct run with its output", "model": DirectRun},
        202: {"description": "The job is accepted"},
        409: {"description": "Idempotency key used for a different request"},
    },
)
async def create_run(
    body: RunRequest,
    request: Request,
    response: Response,
    brevia: BreviaDep,
    caller: CallerDep,
    idempotency_key: IdempotencyKey = None,
) -> Any:
    """Run an activity: directly, answering ``200`` with its ``run_id`` and its
    output, or as a job, answering ``202`` with its state as soon as it is queued.

    ``mode`` may be omitted when the activity supports one mode only. With an
    ``Idempotency-Key``, submitting the same job again gives back the same job.
    """
    caller = acting_for(caller, body.end_user)
    modes = registered(brevia.activities, body.activity).modes
    mode = body.mode
    if mode is None:
        if len(modes) > 1:
            raise InvalidInput(
                "The activity supports both modes: choose one",
                {"activity": body.activity, "modes": sorted(modes)},
            )
        (mode,) = modes
    if mode == "direct":
        if idempotency_key is not None:
            raise InvalidInput(
                "An idempotency key is accepted only for jobs", {"mode": mode}
            )
        run_id = str(uuid.uuid4())
        output = await brevia.run(
            body.activity, body.input, body.overrides, run_id=run_id, caller=caller
        )
        result = {
            "run_id": run_id,
            "status": "succeeded",
            "output": output_json(output),
        }
        return JSONResponse(result)
    handle = await brevia.submit(
        body.activity,
        body.input,
        body.overrides,
        idempotency_key=idempotency_key,
        caller=caller,
    )
    response.headers["Location"] = str(request.url_for("get_run", run_id=handle.run_id))
    return RunState.of(await handle.status())


@router.get("")
async def list_runs(
    brevia: BreviaDep,
    caller: CallerDep,
    activity: str | None = None,
    status: JobStatus | None = None,
    idempotency_key: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 20,
    cursor: str | None = None,
) -> RunPage:
    """The jobs the caller may see, newest first, with the filters given.

    Pass ``next_cursor`` as ``cursor``, with the same filters, for the next page.
    With ``idempotency_key`` (and ``activity``) the job of a key is found without
    submitting it again.
    """
    if not has_jobs(brevia):
        return RunPage(jobs=[], next_cursor=None)
    page = await brevia.jobs(
        activity=activity,
        status=status,
        idempotency_key=idempotency_key,
        limit=limit,
        cursor=cursor,
        caller=caller,
    )
    return RunPage(
        jobs=[RunState.of(state) for state in page.jobs],
        next_cursor=page.next_cursor,
    )


@router.get("/{run_id}", responses=_ERRORS)
async def get_run(run_id: str, brevia: BreviaDep, caller: CallerDep) -> RunState:
    """The job as recorded now."""
    return RunState.of(await job_of(brevia, run_id, caller).status())


@router.get(
    "/{run_id}/result",
    responses={
        **_ERRORS,
        409: {
            "description": "The job has not ended (``not_ready``), or it failed or "
            "was cancelled (the code of its error)"
        },
    },
)
async def get_result(
    run_id: str, request: Request, brevia: BreviaDep, caller: CallerDep
) -> Any:
    """Output of a job that succeeded.

    A job that failed or was cancelled answers ``409`` with the code, the message and
    the details of its error, and with ``run_id`` and ``retryable`` in the details:
    the request succeeded, the job did not, so the status is never a server error.
    """
    handle = job_of(brevia, run_id, caller)
    state = await handle.status()
    if not state.done:
        raise NotReady(
            "The job has not ended", {"run_id": state.run_id, "status": state.status}
        )
    if state.status != "succeeded":
        error = dict(state.error or {})
        details = dict(error.get("details") or {})
        details |= {"run_id": state.run_id, "retryable": bool(error.get("retryable"))}
        return error_response(
            request,
            409,
            str(error.get("code", "internal")),
            str(error.get("message", "")),
            details,
        )
    output = await handle.result()
    return JSONResponse(output_json(output))


@router.post("/{run_id}/cancel", responses=_ERRORS)
async def cancel_run(run_id: str, brevia: BreviaDep, caller: CallerDep) -> RunState:
    """Cancel the job, if it has not ended; calling it again does nothing."""
    return RunState.of(await job_of(brevia, run_id, caller).cancel())


@router.post(
    "/{run_id}/retry",
    status_code=202,
    responses={**_ERRORS, 409: {"description": "The job has not ended"}},
)
async def retry_run(
    run_id: str,
    request: Request,
    response: Response,
    brevia: BreviaDep,
    caller: CallerDep,
    idempotency_key: IdempotencyKey = None,
) -> RunState:
    """Submit a new job with the input of this failed or cancelled one."""
    handle = await job_of(brevia, run_id, caller).retry(idempotency_key=idempotency_key)
    response.headers["Location"] = str(request.url_for("get_run", run_id=handle.run_id))
    return RunState.of(await handle.status())


@router.get(
    "/{run_id}/files/{name}",
    response_class=FileResponse,
    responses={404: {"description": "No such job or output file"}},
)
async def get_file(
    run_id: str, name: str, brevia: BreviaDep, caller: CallerDep
) -> FileResponse:
    """An output file that the job saved, by name."""
    path = await job_of(brevia, run_id, caller).file(name)
    return FileResponse(path, filename=name)


@router.post(
    "/{run_id}/feedback",
    status_code=201,
    responses={
        404: {"description": "No such recorded run, or the caller may not see it"},
        409: {"description": "Idempotency key used for different feedback"},
    },
)
async def add_feedback(
    run_id: str,
    body: FeedbackBody,
    brevia: BreviaDep,
    caller: CallerDep,
    idempotency_key: IdempotencyKey = None,
) -> Feedback:
    """Add corrections of the output, or a rating, to a run, direct or job.

    Feedback is only added: earlier feedback and the output of the run are kept. With
    an ``Idempotency-Key``, sending the same feedback again gives back the feedback
    already recorded.
    """
    caller = acting_for(caller, body.end_user)
    request = FeedbackRequest.model_validate(body.model_dump(exclude={"end_user"}))
    return await brevia.add_feedback(
        run_id, request, idempotency_key=idempotency_key, caller=caller
    )
