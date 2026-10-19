"""Run the analysis examples with a fake model and a migrated development database.

From the repository root: uv run python examples/analysis_pipeline.py
No provider is called. Brevia still records runs in the configured database.
"""

import asyncio
from typing import Any

from pydantic import BaseModel

from brevia import Brevia, Document, RunContext, Tool, split
from brevia.analysis import (
    EXTRACT_PROMPTS,
    SUMMARIZE_PROMPTS,
    ExtractConfig,
    ExtractRequest,
    SummarizeConfig,
    SummarizeRequest,
    Summary,
    extract,
    extract_document,
    map_reduce,
    refine,
    summarize,
    summarize_document,
)
from brevia.testing import fake_model

MODEL = "openai:example-model"
TEXT = "Invoice INV-1.\n\nDelivery completed.\n\nPayment received."


class Invoice(BaseModel):
    number: str


async def uppercase(ctx: RunContext[Any], text: str) -> str:
    return text.upper()


async def generate_text(
    request: SummarizeRequest, ctx: RunContext[SummarizeConfig]
) -> Summary:
    return await ctx.model().generate(
        instructions=ctx.prompt("summarize").render(language=ctx.config.language),
        user_text=request.text or "",
        output_type=Summary,
        max_attempts=3,
        tools=[Tool("uppercase", "Uppercase a text.", uppercase)],
    )


async def combine_parts(
    request: SummarizeRequest, ctx: RunContext[SummarizeConfig]
) -> Summary:
    pieces = split(Document.from_text(request.text or ""), 20)
    return await map_reduce(
        ctx,
        pieces,
        output_type=Summary,
        map_prompt=ctx.prompt("summarize"),
        combine_prompt=ctx.prompt("summarize_combine"),
        values={"language": "English"},
        max_chars=1000,
    )


async def update_parts(
    request: SummarizeRequest, ctx: RunContext[SummarizeConfig]
) -> Summary:
    return await refine(
        ctx,
        split(Document.from_text(request.text or ""), 20),
        output_type=Summary,
        first_prompt=ctx.prompt("summarize"),
        refine_prompt=ctx.prompt("summarize_refine"),
        values={"language": "English"},
    )


async def summary_of_document(
    request: SummarizeRequest, ctx: RunContext[SummarizeConfig]
) -> Summary:
    return await summarize_document(
        ctx, Document.from_text(request.text or ""), language=ctx.config.language
    )


async def invoice(request: ExtractRequest, ctx: RunContext[ExtractConfig]) -> Invoice:
    return await extract(ctx, request, Invoice)


async def invoice_of_document(
    request: ExtractRequest, ctx: RunContext[ExtractConfig]
) -> Invoice:
    return await extract_document(ctx, Document.from_text(request.text or ""), Invoice)


def register(app: Brevia) -> None:
    """Register independent examples, so their prompts never overwrite one another."""
    for name, function in (
        ("generate", generate_text),
        ("map_reduce", combine_parts),
        ("refine", update_parts),
        ("summarize", summarize),
        ("summarize_document", summary_of_document),
    ):
        app.register_activity(
            name=f"example.{name}",
            version="1",
            function=function,
            input_type=SummarizeRequest,
            output_type=Summary,
            config_type=SummarizeConfig,
            prompts=SUMMARIZE_PROMPTS,
            modes=("direct",),
        )
    for name, extract_function in (
        ("extract", invoice),
        ("extract_document", invoice_of_document),
    ):
        app.register_activity(
            name=f"example.{name}",
            version="1",
            function=extract_function,
            input_type=ExtractRequest,
            output_type=Invoice,
            config_type=ExtractConfig,
            prompts=EXTRACT_PROMPTS,
            modes=("direct",),
        )


async def run_examples(app: Brevia) -> dict[str, BaseModel]:
    """Exercise all examples with final answers chosen by the test, not a provider."""
    results = {}
    for name in app.activities:
        with fake_model({"summary": "Synthetic summary.", "number": "INV-1"}):
            results[name] = await app.run(name, {"text": TEXT})
    return results


async def main() -> None:
    app = Brevia.from_settings()
    register(app)
    async with app:
        for name, result in (await run_examples(app)).items():
            print(name, result.model_dump_json())


if __name__ == "__main__":
    asyncio.run(main())
