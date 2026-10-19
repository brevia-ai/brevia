"""Summary example of the specification, shared by the unit tests.

The project file declares the defaults of the test activities that need them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from brevia import RunContext

MODEL = "openai:test-model"

PROJECT = f"""
[limits]
max_requests = 5

[models."{MODEL}"]
reasoning_levels = ["low"]
prices = {{ input = 1, output = 2 }}

[activities."document.summarize"]
model = "{MODEL}"
max_output_tokens = 1200

[activities."test.any-model"]
model = "{MODEL}"

[activities."test.zero"]
model = "{MODEL}"

[activities."test.aliased"]
language = "en"

[activities."test.typo"]
model = "{MODEL}"
max_output_token = 800

[activities."test.undeclared"]
model = "openai:not-declared"

[activities."test.custom"]
model = "{MODEL}"

[activities."test.held"]
model = "{MODEL}"

[traces]
retention_days = 7
"""
PROMPT = "Summarise the document in {language}. Do not add information."


class SummaryRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str | None = None


class SummaryConfig(BaseModel):
    model: str
    max_output_tokens: int = Field(default=1200, gt=0)
    language: str = "it"


class SummaryResult(BaseModel):
    summary: str


class NoConfig(BaseModel):
    """Configuration of activities that need none."""


async def summarize(
    request: SummaryRequest, ctx: RunContext[SummaryConfig]
) -> SummaryResult:
    language = request.language if request.language is not None else ctx.config.language
    result: SummaryResult = await ctx.model().generate(
        instructions=ctx.prompt("summary").render(language=language),
        user_text=request.text,
        output_type=SummaryResult,
        max_output_tokens=ctx.config.max_output_tokens,
    )
    return result
