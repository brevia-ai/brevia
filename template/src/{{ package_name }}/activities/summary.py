"""Activity text.summarize: a summary of a text, written by a model and checked."""

from collections.abc import Collection
from functools import partial

from brevia import Brevia, RunContext

from ..domain import text
from ..schemas import SummaryConfig, SummaryRequest, SummaryResult

NAME = "text.summarize"
VERSION = "1"
PROMPTS = {"summary": "prompts/summary.md"}
OVERRIDABLE = ("language",)  # paths a request may change


def _problems(result: SummaryResult, *, max_words: int) -> list[str]:
    return text.length_problems(result.summary, max_words)


async def summarize(request: SummaryRequest, ctx: RunContext[SummaryConfig]) -> SummaryResult:
    conf = ctx.config
    result: SummaryResult = await ctx.model().generate(
        instructions=ctx.prompt("summary").render(language=conf.language, max_words=conf.max_words),
        user_text=text.normalize(request.text),
        output_type=SummaryResult,
        validator=partial(_problems, max_words=conf.max_words),
        max_output_tokens=conf.max_output_tokens,
    )
    return result


def register(brevia: Brevia, modes: Collection[str]) -> None:
    brevia.register_activity(
        name=NAME,
        version=VERSION,
        function=summarize,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SummaryConfig,
        prompts=PROMPTS,
        overridable=OVERRIDABLE,
        modes=tuple(modes),
    )
