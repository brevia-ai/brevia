"""Run context: what an activity receives besides its input.

The context uses the values recorded in the snapshot of the run, never the current
project settings: a run uses the configuration, prompts, models and limits it started
with.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Generic

from pydantic import BaseModel, ValidationError
from typing_extensions import TypeVar

from brevia.config.prompts import PromptTemplate
from brevia.errors import InvalidInput, NotFound, Unsupported, validation_details
from brevia.files.files import FileStore, RunFiles
from brevia.models.client import ModelClient
from brevia.models.limits import LimitTracker, RunLimits
from brevia.models.spec import ModelInfo, ModelSpec
from brevia.runs.activities import Capture

ConfigT = TypeVar("ConfigT", bound=BaseModel, default=BaseModel)

SNAPSHOT_FORMAT = 2
"""Version of the snapshot layout, recorded in every snapshot."""


class RunContext(Generic[ConfigT]):
    """Context of one run of an activity.

    Attributes:
        run_id: Identifier of the run.
        activity: Name of the activity.
        config: Resolved and validated configuration.
        log: Logger whose records carry the run identifier and the activity name.
        capture: ``"full"`` when the contents of model calls are recorded, otherwise
            ``"metadata"``.
        retention_days: Days the contents of model calls are kept.
        files: Input files of the run and the outputs it saves.
    """

    def __init__(
        self,
        *,
        run_id: str,
        config: ConfigT,
        snapshot: Mapping[str, Any],
        seconds_left: float | None = None,
        files: FileStore | None = None,
    ) -> None:
        # seconds_left is set by Brevia for a job: the time left to its recorded
        # deadline.
        self.run_id = run_id
        self.files = RunFiles(files, run_id)
        self.activity: str = snapshot["activity"]["name"]
        # The resolved object itself: re-validating its recorded form could change it
        # (aliases, excluded fields). The snapshot is the record of the values used.
        self.config = config
        self.log = logging.LoggerAdapter(
            logging.getLogger(f"brevia.activity.{self.activity}"),
            {"run_id": run_id, "activity": self.activity},
        )
        self._prompts = {
            name: PromptTemplate(name, item["text"], item["source"])
            for name, item in snapshot["prompts"].items()
        }
        self._models = {
            reference: ModelInfo.model_validate(info)
            for reference, info in snapshot["models"].items()
        }
        self._model_overrides: Mapping[str, Any] = snapshot["model_overrides"]
        self.capture: Capture = snapshot["capture"]["mode"]
        self.retention_days: int = snapshot["capture"]["retention_days"]
        self._tracker = LimitTracker(
            RunLimits.model_validate(snapshot["limits"]), seconds_left
        )

    @property
    def usage(self) -> dict[str, Any]:
        """Usage of the run so far."""
        return self._tracker.usage.as_dict()

    def prompt(self, name: str) -> PromptTemplate:
        """Template declared by the activity under ``name``.

        Raises:
            NotFound: The activity does not declare this prompt.
        """
        try:
            return self._prompts[name]
        except KeyError:
            raise NotFound(
                f"Prompt {name!r} is not declared by activity {self.activity!r}",
                {"prompt": name},
            ) from None

    def model(self, override: Mapping[str, Any] | None = None) -> ModelClient:
        """Model of the ``model`` configuration field, ready for generation.

        The field may hold a model reference (``"openai:gpt-6-luna"``) or a full model
        use. ``override`` adjusts it for one use, for example a different reasoning
        level for one step; the request overrides of the model still prevail.

        Raises:
            InvalidInput: The configuration has no valid model.
            Unsupported: The model is not declared in the project, or an option is
                not supported by its declared capabilities.
        """
        configured = getattr(self.config, "model", None)
        if isinstance(configured, str):
            base: dict[str, Any] = {"model": configured}
        elif isinstance(configured, ModelSpec):
            base = configured.model_dump()
        else:
            raise InvalidInput(
                f"Activity {self.activity!r} has no model in its configuration"
            )
        values = {**base, **(override or {}), **self._model_overrides}
        try:
            spec = ModelSpec.model_validate(values)
        except ValidationError as exc:
            raise InvalidInput(
                "The model configuration is not valid", validation_details(exc)
            ) from None
        info = self._models.get(spec.model)
        if info is None:
            raise Unsupported(
                f"Model {spec.model!r} is not declared in the project",
                {"model": spec.model},
            )
        return ModelClient(
            spec,
            info,
            self._tracker,
            log_context={"run_id": self.run_id, "activity": self.activity},
            capture=self.capture == "full",
            context=self,
        )
