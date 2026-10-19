"""The ``summarize`` activity: a summary of a document or a text."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from brevia.analysis.strategies import map_reduce, optional_prompt, refine, with_rules
from brevia.config import defaults
from brevia.files.documents import Document, split
from brevia.files.files import FileSource
from brevia.models import ModelClient, ModelSpec
from brevia.runs.context import RunContext

PROMPTS = Path(__file__).parent / "prompts"

SUMMARIZE_PROMPTS: dict[str, Path] = {
    "summarize": PROMPTS / "summarize.md",
    "summarize_combine": PROMPTS / "summarize_combine.md",
    "summarize_refine": PROMPTS / "summarize_refine.md",
}
"""Prompts of :func:`summarize`, files of the package; each has ``{language}``, and
``summarize_refine`` also ``{previous}``. The names start with ``summarize`` so that an
activity can declare them with the prompts of :func:`extract`. Replace a path to use a
prompt of the project."""

RULES = "summarize_rules"
"""Optional prompt of the project added after the prompt of every call of
:func:`summarize`; the package has none."""

Strategy = Literal["auto", "refine"]


SAME_LANGUAGE = "the language of the document"
"""Value of ``{language}`` in the prompts when no language is set."""


class SummarizeRequest(BaseModel):
    """A document to summarise: a file or a text, exactly one of them.

    Attributes:
        file: Input file (PDF, DOCX or text).
        text: Text to summarise.
        language: Language of the summary, as a name (``"English"``); the configured
            one when not given, and the language of the document when neither is.
    """

    model_config = ConfigDict(extra="forbid")

    file: FileSource | None = None
    text: str | None = None
    language: str | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.file is None) == (self.text is None):
            raise ValueError("give exactly one of file and text")
        return self


class SummarizeConfig(BaseModel):
    """Settings of the ``summarize`` activity.

    Attributes:
        model: Model of every call, as a reference or a full model use; an
            override may change one of its options, such as ``model.reasoning``.
        language: Language of the summary when the request does not give one, as a
            name: it is written in the prompts. Without it, the summary keeps the
            language of the document.
        strategy: For a document longer than ``max_input_chars``: ``"auto"``
            summarises its pieces and combines them (map-reduce); ``"refine"`` updates
            one summary piece by piece.
        max_input_chars: Longest text of one call; a longer document is divided into
            pieces of whole sections.
        max_output_tokens: Most tokens that each call may generate, reasoning
            included; the ``max_tokens`` of the model use when not given.
    """

    model: ModelSpec
    language: str | None = Field(
        default=defaults.SUMMARIZE_LANGUAGE, min_length=1, max_length=40
    )
    strategy: Strategy = defaults.SUMMARIZE_STRATEGY
    max_input_chars: int = Field(default=defaults.SUMMARIZE_MAX_INPUT_CHARS, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)


class Summary(BaseModel):
    """Summary of a document."""

    summary: str


async def summarize(
    request: SummarizeRequest, ctx: RunContext[SummarizeConfig]
) -> Summary:
    """Summary of the file or text of ``request``, as a registered activity.

    Register it with the prompts in :data:`SUMMARIZE_PROMPTS`::

        brevia.register_activity(
            name="summarize", version="1", function=summarize,
            input_type=SummarizeRequest, output_type=Summary,
            config_type=SummarizeConfig, prompts=SUMMARIZE_PROMPTS,
            modes={"direct", "job"},
        )

    Raises:
        InvalidInput: The text is empty, or the file cannot be read.
        Unsupported: The file is not a readable format.
        NotFound, Unavailable, FileTooLarge: The file cannot be obtained.
        OutputInvalid, LimitExceeded, RunTimeout, ProviderError: As ``generate``.
    """
    if request.file is not None:
        document = await ctx.files.read(request.file)
    else:
        document = Document.from_text(request.text or "")
    config = ctx.config
    return await summarize_document(
        ctx,
        document,
        language=request.language or config.language,
        strategy=config.strategy,
        max_input_chars=config.max_input_chars,
        max_output_tokens=config.max_output_tokens,
    )


async def summarize_document(
    ctx: RunContext[Any],
    document: Document,
    *,
    language: str | None = defaults.SUMMARIZE_LANGUAGE,
    strategy: Strategy = defaults.SUMMARIZE_STRATEGY,
    max_input_chars: int = defaults.SUMMARIZE_MAX_INPUT_CHARS,
    max_output_tokens: int | None = None,
    model: ModelClient | None = None,
) -> Summary:
    """Summary of ``document``, for use inside another activity.

    A document within ``max_input_chars`` is summarised in one call with the
    ``summarize`` prompt. A longer one is divided with :func:`brevia.split`, then
    summarised with :func:`map_reduce` (``summarize`` and ``summarize_combine``
    prompts) or, with ``strategy="refine"``, with :func:`refine` (``summarize`` and
    ``summarize_refine`` prompts).
    The activity that calls it declares those prompts, for example
    ``prompts={**SUMMARIZE_PROMPTS, ...}``. When the activity also declares a
    ``summarize_rules`` prompt, without variables, its text is added after the prompt
    of every call: the rules of the project reach every step.

    Raises:
        NotFound: A prompt it needs is not declared by the activity.
        OutputInvalid, LimitExceeded, RunTimeout, ProviderError: As ``generate``.
    """
    client = model or ctx.model()
    values = {"language": language or SAME_LANGUAGE}
    rules = optional_prompt(ctx, RULES)
    text = document.text
    if len(text) <= max_input_chars:
        result: Summary = await client.generate(
            instructions=with_rules(
                ctx.prompt("summarize").render(**values),
                rules.render() if rules is not None else "",
            ),
            user_text=text,
            output_type=Summary,
            max_output_tokens=max_output_tokens,
        )
        return result
    pieces = split(document, max_input_chars)
    if strategy == "refine":
        return await refine(
            ctx,
            pieces,
            output_type=Summary,
            first_prompt=ctx.prompt("summarize"),
            refine_prompt=ctx.prompt("summarize_refine"),
            values=values,
            rules=rules,
            model=client,
            max_output_tokens=max_output_tokens,
        )
    return await map_reduce(
        ctx,
        pieces,
        output_type=Summary,
        map_prompt=ctx.prompt("summarize"),
        combine_prompt=ctx.prompt("summarize_combine"),
        values=values,
        rules=rules,
        max_chars=max_input_chars,
        model=client,
        max_output_tokens=max_output_tokens,
    )
