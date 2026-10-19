"""The ``extract`` activity: data of a document, validated against a schema of the
project."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from brevia.analysis.strategies import optional_prompt, refine, with_rules
from brevia.config import defaults
from brevia.files.documents import Document, split
from brevia.files.files import FileSource
from brevia.models import ModelClient, ModelSpec, Validator
from brevia.runs.context import RunContext

PROMPTS = Path(__file__).parent / "prompts"

EXTRACT_PROMPTS: dict[str, Path] = {
    "extract": PROMPTS / "extract.md",
    "extract_refine": PROMPTS / "extract_refine.md",
}
"""Prompts of :func:`extract`, files of the package: ``extract`` for the whole document
or its first piece, ``extract_refine`` for each following piece, with the data so far
in ``{previous}``. Replace a path to use a prompt of the project; for rules that must
reach every call, declare ``extract_rules`` instead (see :func:`extract_document`)."""

RULES = "extract_rules"
"""Optional prompt of the project added after the prompt of every call of
:func:`extract`; the package has none."""


class ExtractRequest(BaseModel):
    """A document to extract data from: a file or a text, exactly one of them.

    Attributes:
        file: Input file (PDF, DOCX or text).
        text: Text to extract data from.
    """

    model_config = ConfigDict(extra="forbid")

    file: FileSource | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.file is None) == (self.text is None):
            raise ValueError("give exactly one of file and text")
        return self


class ExtractConfig(BaseModel):
    """Settings of an extraction activity; a project may extend it with its fields.

    Attributes:
        model: Model of every call, as a reference or a full model use; an
            override may change one of its options, such as ``model.reasoning``.
        max_input_chars: Longest text of one call; a longer document is divided into
            pieces of whole sections and the data is updated piece by piece.
        max_output_tokens: Most tokens that each call may generate, reasoning
            included; the ``max_tokens`` of the model use when not given.
        max_attempts: Attempts of each call to obtain data valid for the schema and
            the validator.
    """

    model: ModelSpec
    max_input_chars: int = Field(default=defaults.EXTRACT_MAX_INPUT_CHARS, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_attempts: int = Field(default=defaults.GENERATION_MAX_ATTEMPTS, ge=1)


async def extract[OutputT: BaseModel](
    ctx: RunContext[Any],
    request: ExtractRequest,
    output_type: type[OutputT],
    *,
    validator: Validator | None = None,
) -> OutputT:
    """Data of the file or text of ``request``, of type ``output_type``.

    The schema is of the project, so the project writes the activity and calls this
    function. Its configuration is :class:`ExtractConfig` or a subclass. The
    ``validator`` checks the data after every piece of a long document, so it must
    accept partial data; check rules on the whole result after ``extract`` returns.
    Register the activity with the prompts in :data:`EXTRACT_PROMPTS`::

        async def extract_invoice(
            request: ExtractRequest, ctx: RunContext[ExtractConfig]
        ) -> Invoice:
            return await extract(ctx, request, Invoice, validator=check_total)

        brevia.register_activity(
            name="invoice.extract", version="1", function=extract_invoice,
            input_type=ExtractRequest, output_type=Invoice,
            config_type=ExtractConfig, prompts=EXTRACT_PROMPTS,
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
    config: ExtractConfig = ctx.config
    return await extract_document(
        ctx,
        document,
        output_type,
        validator=validator,
        max_input_chars=config.max_input_chars,
        max_output_tokens=config.max_output_tokens,
        max_attempts=config.max_attempts,
    )


async def extract_document[OutputT: BaseModel](
    ctx: RunContext[Any],
    document: Document,
    output_type: type[OutputT],
    *,
    validator: Validator | None = None,
    max_input_chars: int = defaults.EXTRACT_MAX_INPUT_CHARS,
    max_output_tokens: int | None = None,
    max_attempts: int = defaults.GENERATION_MAX_ATTEMPTS,
    model: ModelClient | None = None,
) -> OutputT:
    """Data of ``document`` of type ``output_type``, for use inside another activity.

    A document within ``max_input_chars`` takes one call with the ``extract`` prompt.
    A longer one is divided with :func:`brevia.split` and the data is updated piece by
    piece with :func:`refine` (``extract`` and ``extract_refine`` prompts). Every step
    is validated against the schema and ``validator``. The activity that calls it
    declares those prompts, for example ``prompts={**EXTRACT_PROMPTS, ...}``. When the
    activity also declares an ``extract_rules`` prompt, without variables, its text is
    added after the prompt of every call: the rules of the project reach every piece.

    Raises:
        NotFound: A prompt it needs is not declared by the activity.
        OutputInvalid, LimitExceeded, RunTimeout, ProviderError: As ``generate``.
    """
    client = model or ctx.model()
    rules = optional_prompt(ctx, RULES)
    if len(document.text) <= max_input_chars:
        result: OutputT = await client.generate(
            instructions=with_rules(
                ctx.prompt("extract").render(),
                rules.render() if rules is not None else "",
            ),
            user_text=document.text,
            output_type=output_type,
            validator=validator,
            max_attempts=max_attempts,
            max_output_tokens=max_output_tokens,
        )
        return result
    return await refine(
        ctx,
        split(document, max_input_chars),
        output_type=output_type,
        first_prompt=ctx.prompt("extract"),
        refine_prompt=ctx.prompt("extract_refine"),
        rules=rules,
        validator=validator,
        model=client,
        max_attempts=max_attempts,
        max_output_tokens=max_output_tokens,
    )
