"""Helpers for the integration tests: an activity that calls a model, and settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr

from brevia import Brevia, BreviaSettings, RunContext
from brevia.config.project import load_project
from brevia.db.store import SqlStore

MODEL = "openai:test-model"
PROJECT = f"""
[models."{MODEL}"]
prices = {{ input = 1, output = 2 }}

[activities."test.answer"]
model = "{MODEL}"
"""


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    answer: str


class AnswerConfig(BaseModel):
    model: str


async def answer(request: Question, ctx: RunContext[AnswerConfig]) -> Answer:
    result: Answer = await ctx.model().generate(
        instructions="Answer briefly.", user_text=request.text, output_type=Answer
    )
    return result


def settings_for(url: str, schema: str, **values: Any) -> BreviaSettings:
    return BreviaSettings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=SecretStr(url),
        database_schema=schema,
        **values,
    )


def answering_brevia(tmp_path: Path, settings: BreviaSettings) -> Brevia:
    """Brevia with the ``test.answer`` activity on the database of ``settings``."""
    (tmp_path / "brevia.toml").write_text(PROJECT, encoding="utf-8")
    app = Brevia(
        load_project(tmp_path / "brevia.toml"),
        project_dir=tmp_path,
        store=SqlStore(settings),
    )
    app.register_activity(
        name="test.answer",
        version="1",
        function=answer,
        input_type=Question,
        output_type=Answer,
        config_type=AnswerConfig,
    )
    return app
