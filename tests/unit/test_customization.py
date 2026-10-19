"""Customisations of configuration and prompts, and capture of call contents."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import answers, project_brevia, simulated
from memory_store import MemoryStore
from pydantic import BaseModel
from summary_example import (
    MODEL,
    PROMPT,
    NoConfig,
    SummaryConfig,
    SummaryRequest,
    SummaryResult,
    summarize,
)

from brevia import (
    AccessPolicy,
    Brevia,
    Caller,
    Forbidden,
    InvalidInput,
    ModelSpec,
    NotFound,
    OutputInvalid,
    RunContext,
    Unavailable,
    VersionConflict,
)
from brevia.db.customizations import StoredConfiguration, StoredPrompt
from brevia.db.values import storable_json

pytestmark = pytest.mark.unit

ACTIVITY = "test.custom"
CUSTOM_PROMPT = "Write a summary in {language}, in three sentences."


def register(brevia: Brevia, **options: Any) -> None:
    """``test.custom``: the summary example with customisable fields."""
    brevia.register_activity(
        name=ACTIVITY,
        version="1",
        function=summarize,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SummaryConfig,
        prompts={"summary": "prompts/summary.md"},
        overridable=["language"],
        customizable=["max_output_tokens", "language"],
        **options,
    )


async def run(brevia: Brevia, **overrides: Any) -> None:
    with simulated(answers({"summary": "Short."})):
        await brevia.run(ACTIVITY, {"text": "x"}, overrides)


def last_snapshot(store: MemoryStore) -> dict[str, Any]:
    return dict(list(store.runs.values())[-1].snapshot)


# ---------- configuration ----------


async def test_precedence_and_reset_follow_the_example_of_the_specification(
    brevia: Brevia, store: MemoryStore
) -> None:
    # §7.2.1: file 1200, customisation 1800, request in English; reset returns to
    # 1200 for new runs while the earlier run keeps 1800 in its snapshot.
    register(brevia)
    await brevia.customize_configuration(ACTIVITY, {"max_output_tokens": 1800})
    await run(brevia, language="en")
    (first_id,) = store.runs
    first = store.runs[first_id].snapshot
    assert first["config"]["max_output_tokens"] == 1800
    assert first["config"]["language"] == "en"
    await brevia.reset_configuration(ACTIVITY, ["max_output_tokens"])
    await run(brevia)
    assert last_snapshot(store)["config"]["max_output_tokens"] == 1200
    # The recorded snapshot of the earlier run is unchanged.
    assert store.runs[first_id].snapshot["config"]["max_output_tokens"] == 1800


async def test_customisation_updates_the_given_fields_and_keeps_the_others(
    brevia: Brevia,
) -> None:
    register(brevia)
    await brevia.customize_configuration(ACTIVITY, {"max_output_tokens": 1800})
    state = await brevia.customize_configuration(ACTIVITY, {"language": "fr"})
    assert state.customization == {"max_output_tokens": 1800, "language": "fr"}
    assert state.effective is not None
    assert state.effective["max_output_tokens"] == 1800
    assert state.defaults["max_output_tokens"] == 1200
    assert state.customizable == ["language", "max_output_tokens"]
    assert "max_output_tokens" in state.config_schema["properties"]
    assert state.version == 2


async def test_nested_models_are_customised_field_by_field(brevia: Brevia) -> None:
    class SpecConfig(BaseModel):
        model: ModelSpec = ModelSpec(model=MODEL, max_tokens=500)

    async def nothing(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
        return SummaryResult(summary="-")

    brevia.register_activity(
        name="test.spec",
        version="1",
        function=nothing,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SpecConfig,
        customizable=["model.temperature", "model.max_tokens"],
    )
    await brevia.customize_configuration("test.spec", {"model": {"temperature": 0.2}})
    state = await brevia.customize_configuration(
        "test.spec", {"model": {"max_tokens": 900}}
    )
    assert state.customization == {"model": {"temperature": 0.2, "max_tokens": 900}}
    assert state.effective is not None
    assert state.effective["model"]["model"] == MODEL
    with pytest.raises(InvalidInput, match="not customisable"):
        await brevia.customize_configuration(
            "test.spec", {"model": {"model": "openai:other"}}
        )
    with pytest.raises(InvalidInput, match="cannot be stored") as raised:
        await brevia.customize_configuration(
            "test.spec", {"model": {"temperature": float("nan")}}
        )
    assert "finite" in raised.value.details["reason"]
    state = await brevia.reset_configuration("test.spec", ["model.temperature"])
    assert state.customization == {"model": {"max_tokens": 900}}


@pytest.mark.parametrize(
    ("values", "match"),
    [
        ({"max_output_token": 1}, "unknown fields"),
        ({"model": "openai:other"}, "not customisable"),
        ({"max_output_tokens": 0}, "not valid"),
        ({"language": "fr\x00"}, "cannot be stored"),
    ],
)
async def test_invalid_customisations_are_refused_and_not_stored(
    brevia: Brevia, store: MemoryStore, values: dict[str, Any], match: str
) -> None:
    register(brevia)
    with pytest.raises(InvalidInput, match=match):
        await brevia.customize_configuration(ACTIVITY, values)
    assert store.configurations == {}


async def test_expected_version_detects_concurrent_changes(brevia: Brevia) -> None:
    register(brevia)
    read = await brevia.configuration(ACTIVITY)
    assert read.version == 0
    await brevia.customize_configuration(
        ACTIVITY, {"language": "fr"}, expected_version=read.version
    )
    with pytest.raises(VersionConflict) as raised:
        await brevia.customize_configuration(
            ACTIVITY, {"language": "de"}, expected_version=read.version
        )
    assert raised.value.details == {"expected_version": 0, "current_version": 1}
    assert raised.value.http_status == 412
    with pytest.raises(VersionConflict):
        await brevia.reset_configuration(ACTIVITY, expected_version=0)
    # Without an expected version the last change wins.
    state = await brevia.customize_configuration(ACTIVITY, {"language": "de"})
    assert (state.customization, state.version) == ({"language": "de"}, 2)


async def test_reset_of_everything_and_of_fields_that_may_not_be_reset(
    brevia: Brevia,
) -> None:
    register(brevia)
    await brevia.customize_configuration(
        ACTIVITY, {"language": "fr", "max_output_tokens": 900}, author="admin"
    )
    with pytest.raises(InvalidInput, match="not customisable"):
        await brevia.reset_configuration(ACTIVITY, ["model"])
    with pytest.raises(InvalidInput, match="not in the configuration"):
        await brevia.reset_configuration(ACTIVITY, ["colour"])
    with pytest.raises(InvalidInput, match="list of paths"):
        await brevia.reset_configuration(ACTIVITY, "language")
    state = await brevia.reset_configuration(ACTIVITY, author="admin")
    assert state.customization == {}
    assert state.version == 2
    assert state.updated_by == "admin"


async def test_a_stored_customisation_no_longer_valid_stops_runs(
    brevia: Brevia, store: MemoryStore
) -> None:
    # As after a release that makes a field no longer customisable.
    register(brevia)
    store.configurations[ACTIVITY] = StoredConfiguration(
        {"model": "openai:other"}, 3, None, None
    )
    with pytest.raises(Unavailable, match="change or reset it"):
        await run(brevia)
    assert store.runs == {}
    state = await brevia.configuration(ACTIVITY)
    assert state.effective is None
    assert state.problem is not None
    # The leftover can be removed even though it is not customisable.
    state = await brevia.reset_configuration(ACTIVITY, ["model"])
    assert state.customization == {}
    await run(brevia)


async def test_a_field_removed_by_a_release_can_be_reset_alone(
    brevia: Brevia, store: MemoryStore
) -> None:
    register(brevia)
    store.configurations[ACTIVITY] = StoredConfiguration(
        {"language": "fr", "old_field": 1}, 3, None, None
    )
    state = await brevia.reset_configuration(ACTIVITY, ["old_field"])
    assert state.customization == {"language": "fr"}


async def test_customisations_are_read_for_every_run_and_failures_stop_it(
    brevia: Brevia, store: MemoryStore
) -> None:
    register(brevia)
    store.fail.add("customizations")
    with pytest.raises(Unavailable):
        await run(brevia)
    assert store.runs == {}


async def test_only_administrators_change_customisations(
    tmp_path: Path, store: MemoryStore
) -> None:
    policy = AccessPolicy(admins=frozenset({"admin"}))
    async with project_brevia(tmp_path, store, access=policy) as app:
        register(app)
        user, admin = Caller("backend"), Caller("admin")
        changes = (
            lambda caller: app.customize_configuration(
                ACTIVITY, {"language": "fr"}, caller=caller
            ),
            lambda caller: app.reset_configuration(ACTIVITY, caller=caller),
            lambda caller: app.customize_prompt(
                ACTIVITY, "summary", CUSTOM_PROMPT, caller=caller
            ),
            lambda caller: app.reset_prompt(ACTIVITY, "summary", caller=caller),
        )
        for change in changes:
            with pytest.raises(Forbidden) as caught:
                await change(user)
            assert caught.value.http_status == 403
        assert (await app.configuration(ACTIVITY)).version == 0  # nothing stored
        assert (await app.prompt(ACTIVITY, "summary")).version == 0
        for caller in (admin, None):
            for change in changes:
                await change(caller)
        assert (await app.configuration(ACTIVITY)).version == 4
    shared = AccessPolicy(shared=True)
    async with project_brevia(tmp_path, store, access=shared) as app:
        register(app)
        state = await app.customize_configuration(
            ACTIVITY, {"language": "fr"}, caller=Caller("backend")
        )
        assert state.customization == {"language": "fr"}


async def test_customisation_operations_need_a_started_brevia(tmp_path: Path) -> None:
    app = project_brevia(tmp_path, MemoryStore())
    with pytest.raises(RuntimeError, match="not started"):
        await app.configuration("document.summarize")
    with pytest.raises(RuntimeError, match="not started"):
        await app.prompt("document.summarize", "summary")


async def test_registration_checks_customisable_paths_and_capture(
    brevia: Brevia,
) -> None:
    common: dict[str, Any] = {
        "version": "1",
        "function": summarize,
        "input_type": SummaryRequest,
        "output_type": SummaryResult,
        "config_type": NoConfig,
    }
    with pytest.raises(ValueError, match="Customisable paths"):
        brevia.register_activity(name="test.paths", customizable=["colour"], **common)
    with pytest.raises(ValueError, match="Capture"):
        brevia.register_activity(
            name="test.capture",
            capture="everything",  # type: ignore[arg-type]
            **common,
        )


# ---------- prompts ----------


async def test_prompt_customisation_history_reset_and_restore(
    brevia: Brevia, store: MemoryStore
) -> None:
    register(brevia)
    state = await brevia.prompt(ACTIVITY, "summary")
    assert (state.customization, state.effective, state.version) == (None, PROMPT, 0)
    assert state.variables == ["language"]
    await brevia.customize_prompt(ACTIVITY, "summary", CUSTOM_PROMPT, author="ed")
    await run(brevia)
    prompt = last_snapshot(store)["prompts"]["summary"]
    assert (prompt["text"], prompt["source"], prompt["version"]) == (
        CUSTOM_PROMPT,
        "database",
        1,
    )
    state = await brevia.reset_prompt(ACTIVITY, "summary")
    assert (state.customization, state.effective, state.version) == (None, PROMPT, 2)
    await run(brevia)
    prompt = last_snapshot(store)["prompts"]["summary"]
    assert (prompt["text"], prompt["version"]) == (PROMPT, None)
    history = await brevia.prompt_history(ACTIVITY, "summary")
    assert [(r.version, r.operation) for r in history] == [
        (2, "reset"),
        (1, "customize"),
    ]
    assert history[1].text == CUSTOM_PROMPT
    assert history[1].author == "ed"
    assert history[1].sha256 is not None
    # Restoring a revision is a new customisation with its text.
    state = await brevia.customize_prompt(ACTIVITY, "summary", history[1].text)
    assert (state.effective, state.version) == (CUSTOM_PROMPT, 3)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("Summarise.", "exactly the variables"),
        ("Summarise in {language} for {reader}.", "exactly the variables"),
        ("   ", "blank"),
        ("Summarise in {language}.\x00", "NUL"),
    ],
)
async def test_prompt_text_must_keep_the_variables_of_the_file(
    brevia: Brevia, store: MemoryStore, text: str, match: str
) -> None:
    register(brevia)
    with pytest.raises(InvalidInput, match=match):
        await brevia.customize_prompt(ACTIVITY, "summary", text)
    assert store.prompts == {}


async def test_prompt_versions_and_undeclared_prompts(brevia: Brevia) -> None:
    register(brevia)
    with pytest.raises(NotFound):
        await brevia.prompt(ACTIVITY, "other")
    with pytest.raises(NotFound):
        await brevia.customize_prompt(ACTIVITY, "other", "x")
    await brevia.customize_prompt(ACTIVITY, "summary", CUSTOM_PROMPT)
    with pytest.raises(VersionConflict):
        await brevia.reset_prompt(ACTIVITY, "summary", expected_version=0)


async def test_a_stored_prompt_no_longer_valid_stops_runs(
    brevia: Brevia, store: MemoryStore
) -> None:
    # As after a release that changes the variables of the prompt file.
    register(brevia)
    store.prompts[(ACTIVITY, "summary")] = StoredPrompt("No variables.", 1, None, None)
    with pytest.raises(Unavailable, match="prompt 'summary'"):
        await run(brevia)


# ---------- call contents ----------


async def test_full_capture_records_the_contents_of_every_call(
    brevia: Brevia, store: MemoryStore
) -> None:
    register(brevia, capture="full")
    await run(brevia, language="en")
    outcome = store.only_outcome()
    (call,) = outcome.calls
    assert call.content is not None
    assert call.content.instructions == PROMPT.format(language="en")
    assert call.content.user_text == "x"
    assert call.content.output == {"summary": "Short."}
    assert outcome.contents_expire_at == outcome.finished_at + timedelta(days=7)
    assert last_snapshot(store)["capture"] == {"mode": "full", "retention_days": 7}


async def test_full_capture_keeps_the_contents_of_failed_calls(
    brevia: Brevia, store: MemoryStore
) -> None:
    register(brevia, capture="full")
    with (
        simulated(answers({"wrong": 1}, {"wrong": 2}, {"wrong": 3})),
        pytest.raises(OutputInvalid),
    ):
        await brevia.run(ACTIVITY, {"text": "secret document"})
    (call,) = store.only_outcome().calls
    assert call.content is not None
    assert call.content.user_text == "secret document"
    assert call.content.output is None


async def test_nul_characters_in_captured_contents_are_replaced(
    brevia: Brevia, store: MemoryStore
) -> None:
    # Text extracted from PDF files may contain NUL, which PostgreSQL refuses.
    register(brevia, capture="full")
    with simulated(answers({"summary": "a\x00b"})):
        result = await brevia.run(ACTIVITY, {"text": "page\x00two"})
    assert result == SummaryResult(summary="a\x00b")  # the caller gets it unchanged
    (run,) = store.runs.values()
    assert run.input["text"] == "page\ufffdtwo"
    outcome = store.only_outcome()
    assert outcome.result == {"summary": "a\ufffdb"}
    (call,) = outcome.calls
    assert call.content is not None
    assert call.content.user_text == "page\ufffdtwo"
    assert call.content.output == {"summary": "a\ufffdb"}


async def test_escape_sequence_text_is_not_a_nul_character(
    brevia: Brevia, store: MemoryStore
) -> None:
    # A document may describe JSON escapes: the six characters are ordinary text.
    text = "JSON writes NUL as \\u0000."
    register(brevia, capture="full")
    with simulated(answers({"summary": text})):
        await brevia.run(ACTIVITY, {"text": text})
    (run,) = store.runs.values()
    assert run.input["text"] == text
    assert store.only_outcome().result == {"summary": text}
    assert storable_json({text: [text]}) == {text: [text]}


@pytest.mark.parametrize(
    "value", ["a\x00b", ["a\x00b"], {"a\x00b": 1}, {"k": {"x": "\x00"}}]
)
def test_nul_characters_are_refused_in_strings_and_keys(value: Any) -> None:
    with pytest.raises(ValueError, match="NUL"):
        storable_json(value)


async def test_metadata_capture_records_no_contents(
    brevia: Brevia, store: MemoryStore
) -> None:
    register(brevia)
    await run(brevia)
    outcome = store.only_outcome()
    assert outcome.calls[0].content is None
    assert outcome.contents_expire_at is None
