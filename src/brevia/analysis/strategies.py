"""The ``map_reduce`` and ``refine`` strategies over the pieces of a document."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from brevia.config import defaults
from brevia.config.prompts import PromptTemplate
from brevia.errors import LimitExceeded, NotFound
from brevia.files.documents import Piece
from brevia.models import ModelClient, Validator
from brevia.runs.context import RunContext

PREVIOUS = "previous"
"""Variable of the refine prompt that receives the result so far."""


async def map_reduce[OutputT](
    ctx: RunContext[Any],
    pieces: Sequence[Piece | str],
    *,
    output_type: type[OutputT],
    map_prompt: PromptTemplate,
    combine_prompt: PromptTemplate,
    values: Mapping[str, object] | None = None,
    rules: PromptTemplate | None = None,
    partial_type: type[Any] | None = None,
    max_chars: int | None = None,
    validator: Validator | None = None,
    model: ModelClient | None = None,
    max_attempts: int = defaults.GENERATION_MAX_ATTEMPTS,
    max_output_tokens: int | None = None,
) -> OutputT:
    """One output for each piece, then combined into one output.

    Each piece is the user text of a call with ``map_prompt``; the partial outputs,
    joined as text, are the user text of a call with ``combine_prompt``. When
    ``max_chars`` is given and the partial outputs together are longer, they are
    combined in groups, and the results combined again, until one output is left.
    A round with an output longer than ``max_chars``, or where no two outputs fit
    together, stops the run with ``LimitExceeded`` before its calls.
    A single piece whose partial output is already of ``output_type`` needs no
    combination.

    Args:
        ctx: Context of the run.
        pieces: Pieces of the document, in order, or plain texts.
        output_type: Type of the final output.
        map_prompt: Instructions for each piece, rendered with ``values``.
        combine_prompt: Instructions for the combination, rendered with ``values``.
        values: Variables of both prompts.
        rules: Further instructions of the project, added after the prompt of every
            call (see :func:`refine`); none by default.
        partial_type: Type of the output of each piece; ``output_type`` by default.
        max_chars: Longest user text of a combination; no limit by default.
        validator: Checks of every output of type ``output_type``: the
            combinations, and the partial outputs when they have that type.
        model: Model client of every call; ``ctx.model()`` by default.
        max_attempts: Attempts of each call to obtain a valid output.
        max_output_tokens: Overrides the ``max_tokens`` of the model use.

    Raises:
        ValueError: No pieces, or ``max_chars`` not positive.
        InvalidInput: A prompt has variables different from ``values``, or
            ``rules`` has variables.
        LimitExceeded: The partial outputs are too long to combine within
            ``max_chars``.
        OutputInvalid, LimitExceeded, RunTimeout, ProviderError: As ``generate``.
    """
    texts = _texts(pieces, max_chars)
    client = model or ctx.model()
    variables = dict(values or {})
    extra = rules.render() if rules is not None else ""
    partial = partial_type or output_type
    partial_validator = validator if partial is output_type else None
    if len(texts) > 1 or partial is not output_type:
        # Checked before the first call, so that a wrong prompt costs nothing.
        combine_prompt.render(**variables)
    outputs: list[Any] = []
    for number, text in enumerate(texts, 1):
        ctx.log.info("map_reduce: piece %d of %d", number, len(texts))
        outputs.append(
            await client.generate(
                instructions=with_rules(map_prompt.render(**variables), extra),
                user_text=text,
                output_type=partial,
                validator=partial_validator,
                max_attempts=max_attempts,
                max_output_tokens=max_output_tokens,
            )
        )
    if len(outputs) == 1 and partial is output_type:
        result: OutputT = outputs[0]
        return result
    while True:
        groups = _groups([_as_text(output) for output in outputs], max_chars)
        # Checked before any call of the round: no combination is sent over the size,
        # and a round that would not reduce the outputs never ends.
        too_long = max_chars is not None and any(len(g) > max_chars for g in groups)
        if too_long or len(groups) == len(outputs) > 1:
            raise LimitExceeded(
                "Partial outputs too long to combine within max_chars",
                {"max_chars": max_chars, "outputs": len(outputs)},
            )
        ctx.log.info(
            "map_reduce: combining %d outputs in %d groups", len(outputs), len(groups)
        )
        outputs = [
            await client.generate(
                instructions=with_rules(combine_prompt.render(**variables), extra),
                user_text=group,
                output_type=output_type,
                validator=validator,
                max_attempts=max_attempts,
                max_output_tokens=max_output_tokens,
            )
            for group in groups
        ]
        if len(outputs) == 1:
            final: OutputT = outputs[0]
            return final


async def refine[OutputT](
    ctx: RunContext[Any],
    pieces: Sequence[Piece | str],
    *,
    output_type: type[OutputT],
    first_prompt: PromptTemplate,
    refine_prompt: PromptTemplate,
    values: Mapping[str, object] | None = None,
    rules: PromptTemplate | None = None,
    validator: Validator | None = None,
    model: ModelClient | None = None,
    max_attempts: int = defaults.GENERATION_MAX_ATTEMPTS,
    max_output_tokens: int | None = None,
) -> OutputT:
    """An output from the first piece, updated with each following piece.

    The first piece is the user text of a call with ``first_prompt``. Each following
    piece is the user text of a call with ``refine_prompt``, which receives the result
    so far in its ``{previous}`` variable (JSON for a model, the text itself for a
    string) and returns the updated result. Every step is validated, so the result is
    valid after each piece.

    Args:
        ctx: Context of the run.
        pieces: Pieces of the document, in order, or plain texts.
        output_type: Type of the result.
        first_prompt: Instructions for the first piece, rendered with ``values``.
        refine_prompt: Instructions for the following pieces, rendered with
            ``values`` and ``previous``.
        values: Variables of both prompts, without ``previous``.
        rules: Further instructions of the project, without variables, added after
            the prompt of every call, so that a rule written once reaches every
            step; none by default.
        validator: Checks of the result after each step.
        model: Model client of every call; ``ctx.model()`` by default.
        max_attempts: Attempts of each call to obtain a valid output.
        max_output_tokens: Overrides the ``max_tokens`` of the model use.

    Raises:
        ValueError: No pieces, or ``values`` contains ``previous``.
        InvalidInput: A prompt has variables different from those given, or
            ``rules`` has variables.
        OutputInvalid, LimitExceeded, RunTimeout, ProviderError: As ``generate``.
    """
    texts = _texts(pieces, None)
    variables = dict(values or {})
    if PREVIOUS in variables:
        raise ValueError(f"values must not contain {PREVIOUS!r}: refine sets it")
    extra = rules.render() if rules is not None else ""
    if len(texts) > 1:
        # Checked before the first call, so that a wrong prompt costs nothing.
        refine_prompt.render(**variables, previous="")
    client = model or ctx.model()

    async def step(number: int, instructions: str) -> OutputT:
        ctx.log.info("refine: piece %d of %d", number, len(texts))
        output: OutputT = await client.generate(
            instructions=instructions,
            user_text=texts[number - 1],
            output_type=output_type,
            validator=validator,
            max_attempts=max_attempts,
            max_output_tokens=max_output_tokens,
        )
        return output

    result = await step(1, with_rules(first_prompt.render(**variables), extra))
    for number in range(2, len(texts) + 1):
        previous = _as_text(result)
        instructions = refine_prompt.render(**variables, previous=previous)
        result = await step(number, with_rules(instructions, extra))
    return result


def optional_prompt(ctx: RunContext[Any], name: str) -> PromptTemplate | None:
    """The prompt ``name`` of the activity, ``None`` when it does not declare it."""
    try:
        return ctx.prompt(name)
    except NotFound:
        return None


def with_rules(instructions: str, rules: str) -> str:
    """``instructions`` followed by the rules of the project, when there are any."""
    return f"{instructions}\n\n{rules}" if rules else instructions


def _texts(pieces: Sequence[Piece | str], max_chars: int | None) -> list[str]:
    if not pieces:
        raise ValueError("No pieces to analyse")
    if max_chars is not None and max_chars <= 0:
        raise ValueError("max_chars must be positive")
    return [piece.text if isinstance(piece, Piece) else piece for piece in pieces]


def _as_text(value: object) -> str:
    """Text form of an output given back to the model."""
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2)
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def _groups(texts: list[str], max_chars: int | None) -> list[str]:
    """Consecutive texts joined in groups of at most ``max_chars`` characters; a text
    longer than that is a group of its own."""
    if max_chars is None:
        return ["\n\n".join(texts)]
    groups: list[list[str]] = []
    length = 0
    for text in texts:
        if groups and length + 2 + len(text) <= max_chars:
            groups[-1].append(text)
            length += 2 + len(text)
        else:
            groups.append([text])
            length = len(text)
    return ["\n\n".join(group) for group in groups]
