"""Configuration and prompts of the activities: read, customise, reset.

Every caller with a valid token reads them; under the ``per-caller`` policy only
administrators change them. A change made with ``expected_version`` is refused with
``412 version_conflict`` when the customisation was changed meanwhile. The author of a
change is the ``end_user`` given in its body, or the caller itself.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from brevia.access.access import Caller
from brevia.api.requests import BreviaDep, CallerDep, EndUser, acting_for
from brevia.config.customization import ConfigurationState, PromptRevision, PromptState

configurations = APIRouter(prefix="/configurations", tags=["configurations"])
prompts = APIRouter(prefix="/prompts", tags=["prompts"])

_WRITE: dict[int | str, dict[str, Any]] = {
    403: {"description": "Only administrators may change customisations"},
    404: {"description": "Not registered or not declared"},
    412: {"description": "The customisation was changed meanwhile"},
}


class ConfigurationChange(BaseModel):
    """Fields to customise, by name; the others keep their customisation."""

    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any]
    expected_version: int | None = None
    end_user: EndUser = None


class ConfigurationReset(BaseModel):
    """Dotted paths to return to the project defaults; all of them when omitted."""

    model_config = ConfigDict(extra="forbid")

    fields: list[str] | None = None
    expected_version: int | None = None
    end_user: EndUser = None


class PromptChange(BaseModel):
    """New text of a prompt, with exactly the variables of its file."""

    model_config = ConfigDict(extra="forbid")

    text: str
    expected_version: int | None = None
    end_user: EndUser = None


class PromptReset(BaseModel):
    """Return a prompt to the text of its file."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = None
    end_user: EndUser = None


def author(caller: Caller) -> str:
    """Who makes a change, as recorded with it."""
    return caller.end_user or caller.name


# ---------- configuration ----------


@configurations.get("")
async def list_configurations(
    brevia: BreviaDep, caller: CallerDep
) -> list[ConfigurationState]:
    """The configuration of every activity, by name."""
    return [await brevia.configuration(name) for name in sorted(brevia.activities)]


@configurations.get("/{activity}", responses={404: {"description": "Not registered"}})
async def get_configuration(
    activity: str, brevia: BreviaDep, caller: CallerDep
) -> ConfigurationState:
    """Defaults, customisation, effective values, schema and version."""
    return await brevia.configuration(activity)


@configurations.patch("/{activity}", responses=_WRITE)
async def customize_configuration(
    activity: str, change: ConfigurationChange, brevia: BreviaDep, caller: CallerDep
) -> ConfigurationState:
    """Customise some fields; the change applies to the next runs and jobs."""
    caller = acting_for(caller, change.end_user)
    return await brevia.customize_configuration(
        activity,
        change.values,
        expected_version=change.expected_version,
        author=author(caller),
        caller=caller,
    )


@configurations.post("/{activity}/reset", responses=_WRITE)
async def reset_configuration(
    activity: str, reset: ConfigurationReset, brevia: BreviaDep, caller: CallerDep
) -> ConfigurationState:
    """Return some fields, or all of them, to the project defaults."""
    caller = acting_for(caller, reset.end_user)
    return await brevia.reset_configuration(
        activity,
        reset.fields,
        expected_version=reset.expected_version,
        author=author(caller),
        caller=caller,
    )


# ---------- prompts ----------


@prompts.get("")
async def list_prompts(brevia: BreviaDep, caller: CallerDep) -> list[PromptState]:
    """Every prompt of every activity, by activity and name."""
    return [
        await brevia.prompt(name, prompt)
        for name, activity in sorted(brevia.activities.items())
        for prompt in sorted(activity.prompts)
    ]


@prompts.get("/{activity}/{name}", responses={404: {"description": "Not declared"}})
async def get_prompt(
    activity: str, name: str, brevia: BreviaDep, caller: CallerDep
) -> PromptState:
    """File text, customisation, effective text, variables and version."""
    return await brevia.prompt(activity, name)


@prompts.get(
    "/{activity}/{name}/revisions", responses={404: {"description": "Not declared"}}
)
async def get_prompt_revisions(
    activity: str, name: str, brevia: BreviaDep, caller: CallerDep
) -> list[PromptRevision]:
    """Changes of the prompt, the most recent first."""
    return await brevia.prompt_history(activity, name)


@prompts.put("/{activity}/{name}", responses=_WRITE)
async def customize_prompt(
    activity: str,
    name: str,
    change: PromptChange,
    brevia: BreviaDep,
    caller: CallerDep,
) -> PromptState:
    """Replace the text for the next runs; to restore a revision, send its text."""
    caller = acting_for(caller, change.end_user)
    return await brevia.customize_prompt(
        activity,
        name,
        change.text,
        expected_version=change.expected_version,
        author=author(caller),
        caller=caller,
    )


@prompts.post("/{activity}/{name}/reset", responses=_WRITE)
async def reset_prompt(
    activity: str, name: str, reset: PromptReset, brevia: BreviaDep, caller: CallerDep
) -> PromptState:
    """Return the prompt to the text of its file; the history is kept."""
    caller = acting_for(caller, reset.end_user)
    return await brevia.reset_prompt(
        activity,
        name,
        expected_version=reset.expected_version,
        author=author(caller),
        caller=caller,
    )
