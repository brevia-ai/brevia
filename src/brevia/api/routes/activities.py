"""Activities: what the application has registered, with the schemas of each."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from brevia.api.requests import BreviaDep, get_caller
from brevia.errors import NotFound
from brevia.runs.activities import Activity, Mode

# Only callers with a valid token see the activities; all of them see all.
router = APIRouter(
    prefix="/activities", tags=["activities"], dependencies=[Depends(get_caller)]
)


class ActivitySummary(BaseModel):
    """An activity in the list."""

    name: str
    version: str
    modes: list[Mode]


class ActivityDetail(ActivitySummary):
    """An activity with what a caller needs to run it."""

    overridable: list[str]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


@router.get("")
async def list_activities(brevia: BreviaDep) -> list[ActivitySummary]:
    """The registered activities, by name."""
    return [_summary(activity) for _, activity in sorted(brevia.activities.items())]


@router.get("/{name}", responses={404: {"description": "Not registered"}})
async def get_activity(name: str, brevia: BreviaDep) -> ActivityDetail:
    """An activity, with the JSON schemas of its input and output and the
    configuration paths a request may override."""
    activity = registered(brevia.activities, name)
    return ActivityDetail(
        **_summary(activity).model_dump(),
        overridable=sorted(activity.overridable),
        input_schema=activity.input_type.model_json_schema(mode="validation"),
        # As the outputs are returned: by alias, with the computed fields.
        output_schema=activity.output_type.model_json_schema(mode="serialization"),
    )


def registered(activities: Mapping[str, Activity], name: str) -> Activity:
    """The activity ``name``, as :class:`~brevia.Brevia` finds it.

    Raises:
        NotFound: The activity is not registered.
    """
    activity = activities.get(name)
    if activity is None:
        raise NotFound(f"Activity {name!r} is not registered", {"activity": name})
    return activity


def _summary(activity: Activity) -> ActivitySummary:
    return ActivitySummary(
        name=activity.name, version=activity.version, modes=sorted(activity.modes)
    )
