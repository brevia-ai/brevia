"""Activity definitions.

An activity is an application feature with typed input and output: an ``async``
function that receives the validated input and a
:class:`~brevia.runs.context.RunContext`.
It may be deterministic, call a model along a fixed path or let an agent choose its
steps; these forms combine freely and share the same contract.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from brevia.config.prompts import PromptTemplate
from brevia.models.limits import RunLimits

if TYPE_CHECKING:
    from brevia.runs.context import RunContext

Mode = Literal["direct", "job"]
"""How an activity can be run: a direct call or a durable job (``Brevia.submit``)."""

Capture = Literal["metadata", "full"]
"""What is recorded of each model call: usage only, or also its contents."""

ActivityFunction = Callable[[Any, "RunContext[Any]"], Awaitable[BaseModel]]
"""``async def activity(request: In, ctx: RunContext[Config]) -> Out``."""

NAME = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)*$")


@dataclass(frozen=True)
class Activity:
    """A registered activity.

    Attributes:
        name: Unique dotted name, for example ``"document.summarize"``.
        version: Version of the contract (input, output and configuration schemas).
        function: Implementation.
        input_type: Schema of the input.
        output_type: Schema of the output.
        config_type: Schema of the configuration.
        defaults: Project defaults of the configuration.
        overridable: Dotted configuration paths a request may override.
        customizable: Dotted configuration paths the database may customise.
        prompts: Templates the activity uses, by name.
        modes: Supported modes.
        limits: Per-run limits.
        capture: What is recorded of each model call.
    """

    name: str
    version: str
    function: ActivityFunction
    input_type: type[BaseModel]
    output_type: type[BaseModel]
    config_type: type[BaseModel]
    defaults: Mapping[str, Any]
    overridable: frozenset[str]
    customizable: frozenset[str]
    prompts: Mapping[str, PromptTemplate]
    modes: frozenset[Mode]
    limits: RunLimits
    capture: Capture
