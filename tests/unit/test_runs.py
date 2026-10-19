"""Lifecycle and recording of direct runs, with the store in memory."""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import answers, project_brevia, responder, simulated, together
from memory_store import MemoryStore
from pydantic import BaseModel
from summary_example import (
    MODEL,
    NoConfig,
    SummaryRequest,
    SummaryResult,
)

from brevia import (
    Brevia,
    Caller,
    InternalError,
    InvalidInput,
    LimitExceeded,
    ModelSpec,
    OutputInvalid,
    RunContext,
    RunLimits,
    Unavailable,
)

pytestmark = pytest.mark.unit

TEXT = "The confidential document."


async def test_run_needs_a_started_brevia(tmp_path: Path) -> None:
    store = MemoryStore()
    app = project_brevia(tmp_path, store)
    with pytest.raises(RuntimeError, match="not started"):
        await app.run("document.summarize", {"text": "x"})
    async with app:
        with pytest.raises(RuntimeError, match="already started"):
            await app.start()
    await app.stop()  # a second stop is harmless
    assert store.events == ["start", "stop", "stop"]
    assert store.runs == {}


async def test_start_reports_an_unavailable_store(tmp_path: Path) -> None:
    store = MemoryStore(fail={"start"})
    app = project_brevia(tmp_path, store)
    with pytest.raises(Unavailable):
        await app.start()
    with pytest.raises(RuntimeError, match="not started"):
        await app.run("document.summarize", {"text": "x"})


async def test_successful_run_is_recorded_with_snapshot_usage_and_calls(
    brevia: Brevia, store: MemoryStore
) -> None:
    with simulated(answers({"summary": "Short."})):
        await brevia.run("document.summarize", {"text": TEXT}, {"language": "en"})
    (run,) = store.runs.values()
    assert run.activity == "document.summarize"
    assert run.activity_version == "1"
    assert run.mode == "direct"
    assert run.input == {"text": TEXT, "language": None}
    assert run.snapshot["config"]["language"] == "en"
    assert run.snapshot["library"]["name"] == "brevia"
    assert run.snapshot["application"] == {"version": None}
    outcome = store.only_outcome()
    assert outcome.id == run.id
    assert outcome.status == "succeeded"
    assert outcome.result == {"summary": "Short."}
    assert outcome.error is None
    assert outcome.usage["requests"] == 1
    assert outcome.finished_at >= run.started_at
    (call,) = outcome.calls
    assert call.model == MODEL
    # Effective options: max_output_tokens of the activity replaced the model default.
    assert call.options == {"reasoning": None, "temperature": None, "max_tokens": 1200}
    assert call.prices is not None
    assert call.prices.output == Decimal(2)
    assert call.cost_usd == Decimal("0.00012")  # 100 input and 10 output tokens
    assert call.started_at >= run.started_at
    assert outcome.adapter["name"] == "pydantic-ai"


async def test_a_run_records_its_caller(brevia: Brevia, store: MemoryStore) -> None:
    caller = Caller("backend", end_user="user-7")
    with simulated(answers({"summary": "Short."}, {"summary": "Short."})):
        await brevia.run("document.summarize", {"text": TEXT}, caller=caller)
        await brevia.run("document.summarize", {"text": TEXT})
    recorded = {(run.caller, run.end_user) for run in store.runs.values()}
    assert recorded == {("backend", "user-7"), (None, None)}


async def test_snapshot_records_the_application_version(
    tmp_path: Path, store: MemoryStore
) -> None:
    app = project_brevia(tmp_path, store, app_version="2026.10.1")
    async with app:
        with simulated(answers({"summary": "Short."})):
            await app.run("document.summarize", {"text": TEXT})
    (run,) = store.runs.values()
    assert run.snapshot["application"] == {"version": "2026.10.1"}


async def test_run_identifier_is_the_record_key_and_the_log_identifier(
    brevia: Brevia, store: MemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO), simulated(answers({"summary": "Short."})):
        await brevia.run("document.summarize", {"text": TEXT})
    (run_id,) = store.runs
    logged = {getattr(r, "run_id", None) for r in caplog.records} - {None}
    assert logged == {str(run_id)}


async def test_failed_runs_are_recorded_with_their_error(
    brevia: Brevia, store: MemoryStore
) -> None:
    async def broken(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        raise RuntimeError(TEXT)

    brevia.register_activity(
        name="test.broken",
        version="1",
        function=broken,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    invalid = answers({"wrong": 1}, {"wrong": 2}, {"wrong": 3})
    with simulated(invalid), pytest.raises(OutputInvalid):
        await brevia.run("document.summarize", {"text": "x"})
    with pytest.raises(InternalError) as caught:
        await brevia.run("test.broken", {"text": "x"})
    # Neither the error nor a standard traceback of the caller shows the message.
    assert TEXT not in "".join(traceback.format_exception(caught.value))
    by_activity = {store.runs[o.id].activity: o for o in store.outcomes.values()}
    invalid_outcome = by_activity["document.summarize"]
    assert invalid_outcome.status == "failed"
    assert invalid_outcome.result is None
    assert invalid_outcome.error is not None
    assert invalid_outcome.error["code"] == "output_invalid"
    assert len(invalid_outcome.calls) == 1
    assert invalid_outcome.calls[0].error == "output_invalid"
    internal = by_activity["test.broken"].error
    assert internal is not None
    assert internal["code"] == "internal"
    assert TEXT not in str(internal)  # only the type of the unexpected exception


async def test_cancelled_run_is_recorded(brevia: Brevia, store: MemoryStore) -> None:
    started = asyncio.Event()

    async def waits(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        started.set()
        await asyncio.sleep(10)
        return SummaryResult(summary="never")

    brevia.register_activity(
        name="test.waits",
        version="1",
        function=waits,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    task = asyncio.create_task(brevia.run("test.waits", {"text": "x"}))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.only_outcome().status == "cancelled"


async def test_cancellation_prevails_when_it_cannot_be_recorded(
    brevia: Brevia, store: MemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    started = asyncio.Event()

    async def waits(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        started.set()
        await asyncio.sleep(10)
        return SummaryResult(summary="never")

    brevia.register_activity(
        name="test.waits",
        version="1",
        function=waits,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    store.fail.add("finish_run")
    task = asyncio.create_task(brevia.run("test.waits", {"text": "x"}))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with caplog.at_level(logging.WARNING), pytest.raises(asyncio.CancelledError):
        await task
    assert any("Cancelled run not recorded" in r.getMessage() for r in caplog.records)


async def test_run_is_not_started_when_it_cannot_be_recorded(
    brevia: Brevia, store: MemoryStore
) -> None:
    store.fail.add("create_run")
    model = answers({"summary": "Short."})
    with simulated(model), pytest.raises(Unavailable):
        await brevia.run("document.summarize", {"text": "x"})
    assert store.runs == {}


async def test_output_is_not_returned_when_its_outcome_cannot_be_recorded(
    brevia: Brevia, store: MemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    store.fail.add("finish_run")
    with (
        caplog.at_level(logging.INFO),
        simulated(answers({"summary": "Short."})),
        pytest.raises(Unavailable),
    ):
        await brevia.run("document.summarize", {"text": "x"})
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("Run outcome not recorded") for m in messages)
    assert not any(m.startswith("Run succeeded") for m in messages)


async def test_recording_failure_keeps_the_run_error_as_context(
    brevia: Brevia, store: MemoryStore
) -> None:
    store.fail.add("finish_run")
    invalid = answers({"wrong": 1}, {"wrong": 2}, {"wrong": 3})
    with simulated(invalid), pytest.raises(Unavailable) as raised:
        await brevia.run("document.summarize", {"text": "x"})
    assert isinstance(raised.value.__context__, OutputInvalid)


async def test_recording_failure_does_not_chain_an_unexpected_exception(
    brevia: Brevia, store: MemoryStore
) -> None:
    async def broken(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        raise RuntimeError(TEXT)

    brevia.register_activity(
        name="test.broken",
        version="1",
        function=broken,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    store.fail.add("finish_run")
    with pytest.raises(Unavailable) as raised:
        await brevia.run("test.broken", {"text": "x"})
    assert TEXT not in "".join(traceback.format_exception(raised.value))


async def test_recording_can_be_disabled(tmp_path: Path) -> None:
    store = MemoryStore()
    async with project_brevia(tmp_path, store, record_direct_runs=False) as app:
        with simulated(answers({"summary": "Short."})):
            await app.run("document.summarize", {"text": "x"})
    assert store.summary() == {"runs": 0, "statuses": []}


async def test_error_details_are_recorded_as_json(
    brevia: Brevia, store: MemoryStore
) -> None:
    async def refuses(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        raise InvalidInput("Amount too high", {"amount": Decimal("1.50")})

    brevia.register_activity(
        name="test.refuses",
        version="1",
        function=refuses,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    with pytest.raises(InvalidInput):
        await brevia.run("test.refuses", {"text": "x"})
    error = store.only_outcome().error
    assert error is not None
    assert error["details"] == {"amount": "1.50"}


async def test_cancellation_during_the_outcome_write_keeps_the_outcome(
    tmp_path: Path,
) -> None:
    store = MemoryStore(finish_delay=0.1)
    async with project_brevia(tmp_path, store) as app:
        with simulated(answers({"summary": "Short."})):
            task = asyncio.create_task(app.run("document.summarize", {"text": "x"}))
            await asyncio.wait_for(store.finishing.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    # stop() waited for the shielded write
    assert store.only_outcome().status == "succeeded"


async def test_a_failed_outcome_write_after_a_cancellation_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The caller is cancelled while the outcome is written: nobody awaits the write
    # any more, so its failure is logged, with the types of its causes only.
    store = MemoryStore(finish_delay=0.1)
    store.fail.add("finish_run")
    with caplog.at_level(logging.ERROR):
        async with project_brevia(tmp_path, store) as app:
            with simulated(answers({"summary": "Short."})):
                task = asyncio.create_task(
                    app.run("document.summarize", {"text": TEXT})
                )
                await asyncio.wait_for(store.finishing.wait(), 5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
    (logged,) = [
        r
        for r in caplog.records
        if r.getMessage().startswith("Run outcome not recorded after cancellation")
    ]
    assert "Unavailable" in logged.getMessage()
    assert TEXT not in logged.getMessage()
    assert store.outcomes == {}


async def test_a_run_ending_after_stop_fails_with_unavailable(tmp_path: Path) -> None:
    store = MemoryStore()
    app = project_brevia(tmp_path, store)
    release = asyncio.Event()

    started = asyncio.Event()

    async def waits(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        started.set()
        await release.wait()
        return SummaryResult(summary="late")

    app.register_activity(
        name="test.waits",
        version="1",
        function=waits,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    await app.start()
    task = asyncio.create_task(app.run("test.waits", {"text": "x"}))
    await asyncio.wait_for(started.wait(), 5)
    store.fail.add("finish_run")  # as a stopped database store does
    await app.stop()
    release.set()
    with pytest.raises(Unavailable):
        await task


async def test_values_without_a_finite_json_form_are_refused_or_failed(
    brevia: Brevia, store: MemoryStore
) -> None:
    class Measure(BaseModel):
        value: float

    async def echo(request: Measure, ctx: RunContext) -> Measure:
        return Measure(value=float("inf") if request.value == 0 else request.value)

    brevia.register_activity(
        name="test.echo",
        version="1",
        function=echo,
        input_type=Measure,
        output_type=Measure,
        config_type=NoConfig,
    )
    with pytest.raises(InvalidInput, match="cannot be recorded"):
        await brevia.run("test.echo", {"value": float("nan")})
    assert store.runs == {}
    with pytest.raises(InternalError, match="cannot be recorded"):
        await brevia.run("test.echo", {"value": 0})
    outcome = store.only_outcome()
    assert outcome.status == "failed"
    assert outcome.error is not None
    assert outcome.error["code"] == "internal"


async def test_model_overrides_without_a_json_form_are_recorded(
    brevia: Brevia, store: MemoryStore
) -> None:
    class SpecConfig(BaseModel):
        model: ModelSpec | str = MODEL

    async def short(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        result: SummaryResult = await ctx.model().generate(
            instructions="Summarise.", user_text=request.text, output_type=SummaryResult
        )
        return result

    brevia.register_activity(
        name="test.spec",
        version="1",
        function=short,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SpecConfig,
        overridable=["model"],
    )
    model = {"model": MODEL, "temperature": Decimal("0.2")}  # as a Python caller
    with simulated(answers({"summary": "Short."})):
        await brevia.run("test.spec", {"text": "x"}, {"model": model})
    (run,) = store.runs.values()
    assert run.snapshot["model_overrides"] == {"model": MODEL, "temperature": "0.2"}
    assert store.only_outcome().status == "succeeded"


async def test_error_details_without_a_json_form_are_dropped(
    brevia: Brevia, store: MemoryStore
) -> None:
    async def refuses(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        raise InvalidInput("Not finite", {"value": float("nan")})

    brevia.register_activity(
        name="test.nan",
        version="1",
        function=refuses,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=NoConfig,
    )
    with pytest.raises(InvalidInput):
        await brevia.run("test.nan", {"text": "x"})
    error = store.only_outcome().error
    assert error is not None
    assert error["details"] == {}
    assert error["code"] == "invalid_input"


async def test_concurrent_starts_open_the_store_once(tmp_path: Path) -> None:
    store = MemoryStore(start_delay=0.05)
    app = project_brevia(tmp_path, store)
    results = await asyncio.gather(app.start(), app.start(), return_exceptions=True)
    assert sum(isinstance(r, RuntimeError) for r in results) == 1
    await asyncio.gather(app.stop(), app.stop())
    assert store.events == ["start", "stop", "stop"]


class ModelOnly(BaseModel):
    model: str


async def test_run_over_a_limit_fails_even_if_the_activity_catches_the_error(
    tmp_path: Path, store: MemoryStore
) -> None:
    async def two_at_once(
        request: SummaryRequest, ctx: RunContext[ModelOnly]
    ) -> SummaryResult:
        model = ctx.model()
        await asyncio.gather(
            model.generate(instructions="", user_text="a", output_type=SummaryResult),
            model.generate(instructions="", user_text="b", output_type=SummaryResult),
            return_exceptions=True,  # hides the LimitExceeded of the second call
        )
        return SummaryResult(summary="done")

    reply = responder(
        {"summary": "a"}, {"summary": "b"}, input_tokens=30, output_tokens=30
    )
    async with project_brevia(tmp_path, store) as app:
        app.register_activity(
            name="test.any-model",
            version="1",
            function=two_at_once,
            input_type=SummaryRequest,
            output_type=SummaryResult,
            config_type=ModelOnly,
            limits=RunLimits(max_total_tokens=100),
        )
        with simulated(together(2, reply)), pytest.raises(LimitExceeded):
            await app.run("test.any-model", {"text": "x"})
    outcome = store.only_outcome()
    assert outcome.status == "failed"
    assert outcome.error is not None
    assert outcome.error["code"] == "limit_exceeded"


async def test_invalid_input_does_not_chain_the_input_values(brevia: Brevia) -> None:
    document = "".join(["confidential ", "page"])  # not in the source of the test
    with pytest.raises(InvalidInput) as caught:
        await brevia.run("document.summarize", {"text": "x", "language": [document]})
    printed = "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None
    assert document not in printed
    assert caught.value.details  # the problems, without their values


async def test_recorded_options_follow_the_model_override_of_the_activity(
    tmp_path: Path, store: MemoryStore
) -> None:
    async def warmer(
        request: SummaryRequest, ctx: RunContext[ModelOnly]
    ) -> SummaryResult:
        result = await ctx.model({"temperature": 0.3}).generate(
            instructions="",
            user_text="x",
            output_type=SummaryResult,
            max_output_tokens=500,
        )
        return result

    async with project_brevia(tmp_path, store) as app:
        app.register_activity(
            name="test.any-model",
            version="1",
            function=warmer,
            input_type=SummaryRequest,
            output_type=SummaryResult,
            config_type=ModelOnly,
        )
        with simulated(answers({"summary": "ok"})):
            await app.run("test.any-model", {"text": "x"})
    (call,) = store.only_outcome().calls
    assert call.options == {"reasoning": None, "temperature": 0.3, "max_tokens": 500}


async def test_a_direct_run_takes_the_identifier_it_is_given(
    brevia: Brevia, store: MemoryStore
) -> None:
    run_id = str(uuid.uuid4())
    with simulated(answers({"summary": "Breve."})):
        await brevia.run("document.summarize", {"text": "x"}, run_id=run_id)
    assert [str(key) for key in store.runs] == [run_id]
    assert str(store.only_outcome().id) == run_id
    # The same string identifies the run for feedback.
    feedback = await brevia.add_feedback(run_id, {"kind": "rating", "rating": "good"})
    assert feedback.run_id == run_id


async def test_a_run_identifier_that_is_not_a_uuid_is_refused(
    brevia: Brevia, store: MemoryStore
) -> None:
    with pytest.raises(InvalidInput, match="UUID"):
        await brevia.run("document.summarize", {"text": "x"}, run_id="run-1")
    assert store.runs == {}


async def test_the_error_of_a_failed_direct_run_names_the_run(
    brevia: Brevia, store: MemoryStore
) -> None:
    invalid = answers({"wrong": 1}, {"wrong": 2}, {"wrong": 3})
    with simulated(invalid), pytest.raises(OutputInvalid) as raised:
        await brevia.run("document.summarize", {"text": "x"})
    (run_id,) = store.runs
    assert raised.value.details["run_id"] == str(run_id)
    assert OutputInvalid.http_status == 422
    # An error before the run exists names no run.
    with pytest.raises(InvalidInput) as refused:
        await brevia.run("document.summarize", {"text": ""})
    assert "run_id" not in refused.value.details
