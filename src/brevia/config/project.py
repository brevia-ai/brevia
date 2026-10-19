"""Project file: the trusted, versioned configuration of a project.

The project file is a TOML document that declares the models the project may use, with
their capabilities and optional prices, the per-run limits and the default
configuration of each activity::

    [limits]
    max_requests = 20
    max_total_tokens = 200000
    max_seconds = 900

    [models."openai:gpt-6-luna"]
    reasoning_levels = ["low", "medium", "high", "xhigh", "max"]
    temperature_with_reasoning = false
    prices = { input = 0.10, cached_input = 0.01, output = 0.50 }

    [activities."document.summarize"]
    model = "openai:gpt-6-luna"
    language = "it"

    [traces]
    retention_days = 30          # 0, the default, keeps the contents

Capabilities are declared, never inferred from model names. The file contains no
secrets: provider credentials stay in the environment.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from brevia.config import defaults
from brevia.errors import Unavailable, validation_details
from brevia.models.limits import RunLimits
from brevia.models.spec import MODEL_REFERENCE, PROVIDERS, ModelInfo


class TraceSettings(BaseModel):
    """Retention of the contents of model calls (``[traces]`` table)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retention_days: int = Field(
        default=defaults.TRACE_RETENTION_DAYS,
        ge=0,
        le=3650,
        description="Days the contents of model calls are kept after the run ends; "
        "0 keeps them without a time limit.",
    )


class ProjectSettings(BaseModel):
    """Validated content of the project file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    limits: RunLimits = Field(default_factory=RunLimits)
    traces: TraceSettings = Field(default_factory=TraceSettings)
    models: dict[str, ModelInfo] = Field(default_factory=dict)
    activities: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Default configuration of each activity, by activity name.",
    )

    @field_validator("models")
    @classmethod
    def _supported_providers(cls, models: dict[str, ModelInfo]) -> dict[str, ModelInfo]:
        unknown = sorted(
            ref for ref in models if not re.fullmatch(MODEL_REFERENCE, ref)
        )
        if unknown:
            raise ValueError(
                f"model references must be 'provider:name' with a provider among "
                f"{', '.join(PROVIDERS)}: {', '.join(unknown)}"
            )
        return models


def load_project(path: Path) -> ProjectSettings:
    """Read and validate the project file.

    Raises:
        Unavailable: The file cannot be read or is not valid. The message names the
            file only; validation errors are attached as details.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise Unavailable(
            f"Project file cannot be read: {path.name}",
            {"reason": type(exc).__name__},
        ) from exc
    try:
        return ProjectSettings.model_validate(data)
    except ValidationError as exc:
        raise Unavailable(
            f"Project file is not valid: {path.name}",
            validation_details(exc),
        ) from exc
