"""The defaults of Brevia, and the project file of the template that writes them out."""

from __future__ import annotations

from pathlib import Path

import pytest

from brevia.analysis import ExtractConfig, SummarizeConfig
from brevia.config import defaults
from brevia.config.project import load_project
from brevia.errors import LimitExceeded
from brevia.models.limits import LimitTracker, RunLimits, Usage
from brevia.models.spec import ModelSpec

pytestmark = pytest.mark.unit

TEMPLATE = Path(__file__).parents[2] / "template" / "brevia.toml.jinja"


def test_the_classes_take_their_defaults_from_one_module() -> None:
    assert RunLimits().model_dump() == {
        "max_requests": defaults.RUN_MAX_REQUESTS,
        "max_tool_calls": defaults.RUN_MAX_TOOL_CALLS,
        "max_total_tokens": defaults.RUN_MAX_TOTAL_TOKENS,
        "max_seconds": defaults.RUN_MAX_SECONDS,
        "provider_retries": defaults.RUN_PROVIDER_RETRIES,
    }
    assert ModelSpec(model="openai:x").max_tokens == defaults.MODEL_MAX_TOKENS
    summarize = SummarizeConfig.model_validate({"model": "openai:x"})
    assert (summarize.language, summarize.strategy, summarize.max_input_chars) == (
        defaults.SUMMARIZE_LANGUAGE,
        defaults.SUMMARIZE_STRATEGY,
        defaults.SUMMARIZE_MAX_INPUT_CHARS,
    )
    extract = ExtractConfig.model_validate({"model": "openai:x"})
    assert (extract.max_input_chars, extract.max_attempts) == (
        defaults.EXTRACT_MAX_INPUT_CHARS,
        defaults.GENERATION_MAX_ATTEMPTS,
    )


def test_the_template_writes_out_the_defaults_it_does_not_change(
    tmp_path: Path,
) -> None:
    jinja2 = pytest.importorskip("jinja2")
    text = jinja2.Template(TEMPLATE.read_text(encoding="utf-8")).render(
        model="openai:gpt-6-luna"
    )
    path = tmp_path / "brevia.toml"
    path.write_text(text, encoding="utf-8")
    project = load_project(path)

    # max_requests and max_seconds are choices of the template, lower than the defaults.
    assert project.limits.max_tool_calls == defaults.RUN_MAX_TOOL_CALLS
    assert project.limits.max_total_tokens == defaults.RUN_MAX_TOTAL_TOKENS
    assert project.limits.provider_retries == defaults.RUN_PROVIDER_RETRIES
    assert project.traces.retention_days == defaults.TRACE_RETENTION_DAYS
    summarize = SummarizeConfig.model_validate(project.activities["document.summarize"])
    assert summarize == SummarizeConfig(model=ModelSpec(model="openai:gpt-6-luna"))


def test_a_limit_set_to_zero_is_off() -> None:
    off = RunLimits(max_requests=0, max_tool_calls=0, max_total_tokens=0, max_seconds=0)
    tracker = LimitTracker(off)
    budget = tracker.reserve(5)
    assert (budget.requests, budget.tool_calls, budget.tokens, budget.seconds) == (
        5,
        None,
        None,
        None,
    )
    assert tracker.reserve(None).requests is None  # every request, without a limit
    tracker.usage = Usage(requests=10_000, tool_calls=10_000, input_tokens=10**9)
    tracker.check_totals()  # nothing to exceed


def test_a_call_with_tools_reserves_the_requests_left_without_a_tool_limit() -> None:
    tracker = LimitTracker(RunLimits(max_requests=6, max_tool_calls=0))
    assert tracker.reserve(None).requests == 6
    with pytest.raises(LimitExceeded):
        tracker.reserve(None)  # the first call holds them all
