"""Summary example of the specification with a real OpenAI model.

Runs only on request (``uv run --env-file .env pytest -m ai``) and needs
``OPENAI_API_KEY`` and a migrated database at ``BREVIA_DATABASE_URL``, where the run is
recorded; it calls the provider and incurs a small cost.
It checks the behaviour of the library with a real provider (structured output,
usage, cost, logs), not the quality of the summary.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from brevia import Brevia, BreviaSettings, ModelSpec, RunContext

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY is not set"
    ),
    pytest.mark.skipif(
        not os.environ.get("BREVIA_DATABASE_URL"),
        reason="BREVIA_DATABASE_URL is not set",
    ),
]

MODEL = "openai:gpt-6-luna"
# Official OpenAI prices verified on 2026-10-10 (USD per million tokens).
PROJECT = f"""
[limits]
max_requests = 5
max_seconds = 120

[models."{MODEL}"]
reasoning_levels = ["low", "medium", "high"]
temperature = false
prices = {{ input = 0.10, cached_input = 0.01, output = 0.50 }}

[activities."document.summarize"]
model = {{ model = "{MODEL}", reasoning = "low", max_tokens = 2000 }}
"""
PROMPT = (
    "Summarise the document in {language} in at most two sentences.\n"
    "Keep the numbers. Do not add information that is not in the document."
)
DOCUMENT = (
    "In the third quarter the cooperative processed 1,240 tonnes of olives, 18% more "
    "than a year earlier. Oil yield fell to 14.2% because of the dry summer, so total "
    "oil output grew only 6%. The cooperative expects stable prices until March."
)


class SummaryRequest(BaseModel):
    text: str = Field(min_length=1)


class SummaryConfig(BaseModel):
    model: ModelSpec
    language: str = "English"


class SummaryResult(BaseModel):
    """Summary of the document."""

    summary: str = Field(description="The summary, in the requested language.")


def keeps_the_numbers(result: SummaryResult) -> list[str]:
    missing = [n for n in ("1,240", "18%", "14.2%") if n not in result.summary]
    return [f"the summary must keep the number {n}" for n in missing]


async def summarize(
    request: SummaryRequest, ctx: RunContext[SummaryConfig]
) -> SummaryResult:
    result: SummaryResult = await ctx.model().generate(
        instructions=ctx.prompt("summary").render(language=ctx.config.language),
        user_text=request.text,
        output_type=SummaryResult,
        validator=keeps_the_numbers,
    )
    return result


async def test_summary_with_a_real_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    (tmp_path / "summary.md").write_text(PROMPT, encoding="utf-8")
    # The database URL comes from the environment.
    settings = BreviaSettings(project_file=tmp_path / "brevia.toml")  # type: ignore[call-arg]
    brevia = Brevia.from_settings(settings)
    brevia.register_activity(
        name="document.summarize",
        version="1",
        function=summarize,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SummaryConfig,
        prompts={"summary": "summary.md"},
    )
    with caplog.at_level(logging.INFO, logger="brevia"):
        async with brevia:
            result = await brevia.run("document.summarize", {"text": DOCUMENT})

    assert isinstance(result, SummaryResult)
    assert keeps_the_numbers(result) == []
    calls = [r for r in caplog.records if r.getMessage().startswith("Model call")]
    assert calls
    assert all(getattr(r, "run_id", None) for r in calls)
    finished = next(r for r in caplog.records if r.getMessage().startswith("Run succ"))
    assert "cost unknown" not in finished.getMessage()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "cooperative" not in logged  # no document text in the logs
    print("\nSUMMARY:", result.summary)
    print("LOG:", finished.getMessage())
