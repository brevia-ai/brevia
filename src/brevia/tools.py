"""Tools: functions of the code that a model may call during a generation.

A :class:`Tool` wraps an ``async`` function whose first parameter is the
:class:`~brevia.RunContext` of the run; the other parameters, with their types, are
what the model gives. The code chooses the tools of each call::

    report = await ctx.model().generate(
        instructions=...,
        user_text=...,
        output_type=Report,
        tools=[read_file(request.contract), save_file],
    )

Identity, permissions and files come from the run, never from the model. A tool raises
:class:`ToolRetry` for arguments that the model can correct (a wrong name, an index
out of range): its message is sent back to the model. Any other error, also an
``InvalidInput`` of a file that cannot be read, stops the run.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from pydantic import BaseModel

from brevia.errors import InvalidInput
from brevia.files.files import checked_name
from brevia.runs.context import RunContext

if TYPE_CHECKING:
    from brevia.files.documents import Document
    from brevia.files.files import FileSource

__all__ = [
    "READ_MAX_CHARS",
    "FileText",
    "SavedFile",
    "SectionText",
    "Tool",
    "ToolFunction",
    "ToolRetry",
    "read_file",
    "save_file",
]

ToolFunction = Callable[..., Awaitable[Any]]
"""``async def f(ctx: RunContext, ...) -> result``; the result must be JSON-compatible
or a Pydantic model."""

READ_MAX_CHARS = 20_000
"""Default longest text that one call of ``read_file`` returns."""


class ToolRetry(Exception):
    """Arguments of a tool call that the model can correct.

    The message is sent back to the model, which may call the tool again; it must not
    contain secrets. Any other exception raised by a tool stops the run.
    """


@dataclass(frozen=True)
class Tool:
    """A function that a model may call, with the name and description it sees.

    Attributes:
        name: Name of the tool for the model; letters, digits, ``_`` and ``-``.
        description: What the tool does and when to use it, for the model.
        function: ``async`` function; its first parameter receives the context of the
            run, the others are the arguments of the model.
        writes: The tool has external effects; it must be safe to repeat, since a
            generation may be retried.
    """

    name: str
    description: str
    function: ToolFunction
    writes: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.name):
            raise ValueError("Tool name must contain 1-64 letters, digits, '_' or '-'")
        if not inspect.iscoroutinefunction(self.function):
            raise ValueError("Tool function must be async")
        parameters = list(inspect.signature(self.function).parameters.values())
        if not parameters or parameters[0].kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            raise ValueError(
                "Tool function needs the run context as its first parameter"
            )
        # The model gives the arguments by name: each must be a named parameter.
        named = (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        if any(parameter.kind not in named for parameter in parameters[1:]):
            raise ValueError(
                "Tool function arguments must be named parameters: no positional-only "
                "parameters, *args or **kwargs"
            )


class SectionText(BaseModel):
    """A section returned by ``read_file``."""

    title: str | None = None
    page: int | None = None
    text: str


class FileText(BaseModel):
    """Answer of ``read_file``: some sections of a file, from ``start``.

    Attributes:
        name: Name of the file.
        start: Index of the first section returned.
        total: Number of sections of the file.
        sections: Sections returned.
        next_start: Index to give as ``start`` for the following sections; ``None``
            when the file has been read to its end.
        next_offset: Character offset within ``next_start``; pass it as ``offset``.
        truncated: The text of the last section returned was cut at the size of
            one answer.
    """

    name: str
    start: int
    total: int
    sections: list[SectionText]
    next_start: int | None
    truncated: bool
    next_offset: int = 0


class SavedFile(BaseModel):
    """Answer of ``save_file``."""

    name: str
    size: int
    sha256: str


def read_file(*sources: FileSource, max_chars: int = READ_MAX_CHARS) -> Tool:
    """Tool that lets the model read the files ``sources``, some sections at a time.

    The model gives the name of a file, the index of the first section and how many
    to read; the answer holds whole sections up to ``max_chars`` characters and the
    index to continue from. Parsed files are cached per run; concurrent first reads
    may parse twice.
    A cut section is continued with ``next_start`` and ``next_offset``, without
    losing text.

    Raises:
        ValueError: No sources, two sources with the same name, or ``max_chars`` not
            positive.
    """
    if not sources:
        raise ValueError("read_file needs at least one source")
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    by_name = {source.name: source for source in sources}
    if len(by_name) != len(sources):
        raise ValueError("The sources of read_file must have different names")
    files = ", ".join(sorted(by_name))
    cache: WeakKeyDictionary[RunContext[Any], dict[str, Document]] = WeakKeyDictionary()

    async def read(
        ctx: RunContext[Any],
        name: str,
        start: int = 0,
        count: int = 10,
        offset: int = 0,
    ) -> FileText:
        source = by_name.get(name)
        if source is None:
            raise ToolRetry(
                f"Unknown file {name!r}; files: {', '.join(sorted(by_name))}"
            )
        documents = cache.setdefault(ctx, {})
        document = documents.get(name)
        if document is None:
            document = documents[name] = await ctx.files.read(source)
        total = len(document.sections)
        if not 0 <= start < total or count < 1:
            raise ToolRetry(
                f"start must be between 0 and {total - 1}, count at least 1"
            )
        if not 0 <= offset <= len(document.sections[start].text):
            raise ToolRetry("offset must be within the first section")
        sections: list[SectionText] = []
        size, truncated = 0, False
        next_offset = 0
        for index, section in enumerate(document.sections[start : start + count]):
            room = max_chars - size
            if room <= 0:
                break
            begin = offset if index == 0 else 0
            text = section.text[begin:]
            if len(text) > room:
                text, truncated = text[:room], True
                next_offset = begin + room
            sections.append(
                SectionText(title=section.title, page=section.page, text=text)
            )
            size += len(text)
            if truncated:
                break
        end = start + len(sections) - int(truncated)
        return FileText(
            name=name,
            start=start,
            total=total,
            sections=sections,
            next_start=end if end < total else None,
            truncated=truncated,
            next_offset=next_offset,
        )

    return Tool(
        name="read_file",
        description=(
            f"Read the text of a file, some sections at a time. Files: {files}. "
            "Give the name, the index of the first section (start) and how many "
            "sections to read (count); continue from next_start and next_offset "
            "(as offset) until next_start is null."
        ),
        function=read,
    )


async def _save(ctx: RunContext[Any], name: str, text: str) -> SavedFile:
    try:
        checked_name(name)
    except InvalidInput as exc:
        raise ToolRetry(f"Not a valid file name: {exc.message}") from None
    ref = await ctx.files.save(name, text.encode("utf-8"))
    return SavedFile(name=ref.name, size=ref.size, sha256=ref.sha256)


save_file = Tool(
    name="save_file",
    description=(
        "Save a text file among the outputs of the run. The same name replaces the "
        "file. Give the name with its extension (for example notes.md) and the text."
    ),
    function=_save,
    writes=True,
)
"""Tool that lets the model save a UTF-8 text file among the outputs of the run."""
