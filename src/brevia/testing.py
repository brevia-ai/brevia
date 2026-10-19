"""Support for testing activities without a model provider.

:func:`fake_model` replaces every model call with a fake while a block runs, so that a
project tests its activities with predictable outputs and no cost. The fake answers in
place of the provider: limits, validation, retries of invalid outputs and the records
of the run work as with a real model. Runs record ``fake`` as their model adapter.

``BREVIA_FAKE_MODELS=true`` does the same for a whole process, with outputs generated
from the schemas: see :meth:`brevia.Brevia.from_settings`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel

from brevia.models import fake

__all__ = ["fake_model"]


@contextmanager
def fake_model(*outputs: BaseModel | Mapping[str, Any]) -> Iterator[None]:
    """Answer every model call of the process with a fake while the block runs.

    Args:
        *outputs: Outputs returned in order, one per model request, as instances of
            the output type of the call or as their JSON form; the last one is
            repeated when more requests are made. Without outputs, each answer is
            generated from the output schema: valid for the schema, but not
            meaningful, so a validator may refuse it.

    Each request of a scripted fake reports 100 input and 20 output tokens, counted
    against the limits of the run and priced with the declared prices. The fake
    replaces the model only: the model reference must still be declared in the
    project file. The block prevails over ``BREVIA_FAKE_MODELS``; on exit the fake
    of an enclosing block, if any, is in use again.

    Example:
        ```python
        from brevia.testing import fake_model

        with fake_model(SummaryResult(summary="Short.")):
            result = await brevia.run("document.summarize", {"text": "..."})
        assert result.summary == "Short."
        ```
    """
    previous = fake.overriding()
    fake.install(fake.scripted(outputs) if outputs else fake.from_schema())
    try:
        yield
    finally:
        fake.install(previous)
