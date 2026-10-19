"""Requests, configuration and results of the activities (Pydantic models).

Brevia validates the request before a run, the configuration when the activity is registered
and the result before returning it.
"""

from pydantic import BaseModel, Field


class SummaryRequest(BaseModel):
    """What a caller sends."""

    text: str = Field(min_length=1)


class SummaryConfig(BaseModel):
    """Settings of the activity: defaults here, values in brevia.toml."""

    model: str
    language: str = "it"
    max_words: int = Field(default=120, gt=0)
    max_output_tokens: int = Field(default=1200, gt=0)


class SummaryResult(BaseModel):
    """What the activity returns."""

    summary: str
