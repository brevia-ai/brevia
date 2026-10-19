"""Fake models: ``brevia.testing.fake_model`` and ``BREVIA_FAKE_MODELS``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from conftest import project_brevia
from memory_store import MemoryStore
from pydantic import SecretStr
from summary_example import (
    MODEL,
    PROJECT,
    SummaryConfig,
    SummaryRequest,
    SummaryResult,
    summarize,
)

from brevia import Brevia, BreviaSettings, OutputInvalid, RunContext
from brevia.models import fake
from brevia.models import pydantic_ai as adapter_module
from brevia.models.client import ModelClient
from brevia.models.limits import LimitTracker, RunLimits
from brevia.models.spec import ModelInfo, ModelSpec
from brevia.testing import fake_model

pytestmark = pytest.mark.unit

TEXT = "A document about the harvest of 2026."


@pytest.fixture(autouse=True)
def no_provider() -> Iterator[None]:
    """Any call that reaches a real provider fails the test; no fake is left."""
    with patch.object(
        adapter_module, "_resolve_model", side_effect=AssertionError("provider called")
    ):
        yield
    fake.install(None)
    fake.install_default(None)


async def test_a_scripted_fake_answers_in_order_and_repeats_the_last(
    tmp_path: Path, store: MemoryStore
) -> None:
    async with project_brevia(tmp_path, store) as app:
        with fake_model(SummaryResult(summary="One."), {"summary": "Two."}):
            first = await app.run("document.summarize", {"text": TEXT})
            second = await app.run("document.summarize", {"text": TEXT})
            third = await app.run("document.summarize", {"text": TEXT})
    assert [first, second, third] == [
        SummaryResult(summary="One."),
        SummaryResult(summary="Two."),
        SummaryResult(summary="Two."),
    ]
    assert fake.installed() is None  # removed on exit


async def test_runs_with_a_fake_record_it_as_their_adapter(
    tmp_path: Path, store: MemoryStore
) -> None:
    async with project_brevia(tmp_path, store) as app:
        with fake_model({"summary": "Short."}):
            await app.run("document.summarize", {"text": TEXT})
    (run,) = store.runs.values()
    assert run.snapshot["adapter"]["name"] == "fake"
    outcome = store.only_outcome()
    assert outcome.adapter["name"] == "fake"
    (call,) = outcome.calls
    assert (call.input_tokens, call.output_tokens) == (100, 20)
    assert call.cost_usd is not None  # priced with the declared prices


async def test_without_outputs_the_fake_follows_the_schema(
    tmp_path: Path, store: MemoryStore
) -> None:
    async with project_brevia(tmp_path, store) as app:
        with fake_model():
            result = await app.run("document.summarize", {"text": TEXT})
    assert isinstance(result, SummaryResult)


async def test_an_invalid_scripted_output_fails_as_with_a_real_model(
    tmp_path: Path, store: MemoryStore
) -> None:
    async with project_brevia(tmp_path, store) as app:
        with fake_model({"title": "no summary"}), pytest.raises(OutputInvalid):
            await app.run("document.summarize", {"text": TEXT})


async def test_a_fake_used_only_inside_the_activity_is_recorded(
    tmp_path: Path, store: MemoryStore
) -> None:
    # The block ends before the outcome is written: the call keeps its adapter.
    async def faked(request: SummaryRequest, ctx: RunContext[SummaryConfig]) -> Any:
        with fake_model({"summary": "Short."}):
            return await summarize(request, ctx)

    async with project_brevia(tmp_path, store) as app:
        app.register_activity(
            name="test.any-model",
            version="1",
            function=faked,
            input_type=SummaryRequest,
            output_type=SummaryResult,
            config_type=SummaryConfig,
            prompts={"summary": "prompts/summary.md"},
        )
        await app.run("test.any-model", {"text": TEXT})
    outcome = store.only_outcome()
    (call,) = outcome.calls
    assert call.adapter is not None
    assert call.adapter["name"] == "fake"
    assert outcome.adapter["name"] == "fake"


def test_a_block_prevails_over_the_fake_of_the_settings(tmp_path: Path) -> None:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    with fake_model({"summary": "Expected."}):
        scripted = fake.installed()
        Brevia.from_settings(settings_with_fakes(tmp_path))
        assert fake.installed() is scripted  # the block still prevails
    assert fake.installed() is not None  # the fake of the settings remains


def settings_with_fakes(tmp_path: Path) -> BreviaSettings:
    return BreviaSettings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=SecretStr("postgresql://u:p@db/brevia"),
        project_file=tmp_path / "brevia.toml",
        fake_models=True,
    )


def test_fake_models_from_the_settings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    settings = BreviaSettings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=SecretStr("postgresql://u:p@db/brevia"),
        project_file=tmp_path / "brevia.toml",
        fake_models=True,
    )
    Brevia.from_settings(settings)
    assert fake.installed() is not None
    assert any("Fake models in use" in r.getMessage() for r in caplog.records)


def test_a_scripted_fake_needs_an_output() -> None:
    with pytest.raises(ValueError, match="at least one output"):
        fake.scripted([])


async def test_a_fake_accepts_every_declared_reasoning_level() -> None:
    info = ModelInfo(reasoning_levels=frozenset({"high", "max"}))
    for level in ("high", "max"):
        model = ModelClient(
            ModelSpec(model=MODEL, reasoning=level), info, LimitTracker(RunLimits())
        )
        with fake_model(SummaryResult(summary="ok")):
            result = await model.generate(
                instructions="", user_text=TEXT, output_type=SummaryResult
            )
        assert result == SummaryResult(summary="ok")
