# Testing

A project tests its activities without calling a model provider: a **fake model**
answers in place of the provider, so that tests are fast, repeatable and free. The
fake replaces the model only: input validation, configuration, prompts, limits,
validation of the output, retries of invalid outputs and the records of the run work
as with a real model.

| When | Use |
|---|---|
| A unit test needs a given output | [`fake_model(...)`](#fake_model) with the outputs |
| A test only needs a valid output | [`fake_model()`](#fake_model) without outputs |
| A whole process must run without a provider: a local demo, an end-to-end test of the API, a worker | [`BREVIA_FAKE_MODELS=true`](#brevia_fake_models) |

Runs that use a fake record `fake` as their model adapter, in the
[snapshot](runs.md#snapshots) and in each model call, so that their records are never
taken for real ones. Brevia still needs its database: run the tests on a PostgreSQL
database, for example the one of `compose.yaml` in development.

## `fake_model`

[`brevia.testing.fake_model`](../reference/testing.md#brevia.testing.fake_model)
answers every model call of the process with a fake while the block runs. With
outputs, they are returned in order, one per model request, and the last one is
repeated when more requests are made:

```python
import pytest

from brevia import Brevia
from brevia.testing import fake_model
from summary import SummaryResult


async def test_summary_is_returned(brevia: Brevia) -> None:
    with fake_model(SummaryResult(summary="Short.")):
        result = await brevia.run("document.summarize", {"text": "..."})
    assert result == SummaryResult(summary="Short.")
```

An output can be given as an instance of the output type or as its JSON form, a
dictionary. A dictionary that does not fit the schema is useful to test how the
activity handles a model that answers badly:

```python
from brevia import OutputInvalid


async def test_an_invalid_answer_fails_the_run(brevia: Brevia) -> None:
    # Every attempt gets the same invalid answer: the run fails after max_attempts.
    with fake_model({"title": "no summary"}), pytest.raises(OutputInvalid):
        await brevia.run("document.summarize", {"text": "..."})
```

Two outputs test a retry: a first answer that the [validator](models.md) refuses,
then a valid one.

Without outputs, each answer is generated from the output schema: valid for the
schema but not meaningful (strings such as `"a"`, numbers such as `0`). A validator
that checks the content may refuse it, and the run then fails with `OutputInvalid`.

What a scripted fake reports:

| | Value |
|---|---|
| Tokens of each request | 100 input, 20 output, counted against the limits of the run |
| Cost | Estimated with the prices declared for the model reference |
| Model reference | The declared one: it must still be in the project file |
| Reasoning | Not checked: a fake does not reason |

The fake is installed for the whole process, not only for the current task: model
calls of other tasks and of a job worker running in the same process use it too. A
block prevails over the fake of `BREVIA_FAKE_MODELS`, also when the application is
created inside it; on exit, the fake of an enclosing block, or that of the settings,
is in use again. A block may surround a single model call inside an activity: each
call records the adapter that made it, and the run records `fake` when a fake
answered any of its calls. Do not run tests that use
different fakes concurrently in the same process.

## `BREVIA_FAKE_MODELS`

With `BREVIA_FAKE_MODELS=true`, [`Brevia.from_settings`](../reference/application.md#brevia.Brevia.from_settings)
installs a fake that answers every model call of the process with an output generated
from the schema, and logs the warning `Fake models in use: no model provider is
called`. No provider key is needed:

```sh
BREVIA_FAKE_MODELS=true uv run python main.py
BREVIA_FAKE_MODELS=true uv run brevia worker app:brevia
```

It is meant for local runs, demonstrations and end-to-end tests, never for
production: the outputs are not meaningful. It applies to applications created with
`Brevia.from_settings`; a `fake_model` block inside the same process takes precedence
while it runs.

## What a fake does not prove

A fake proves the behaviour of the code around the model: the activity, its
configuration, its limits, its records. It does not prove the quality of a real model,
nor that a prompt gives good answers: that needs tests with a real provider, run on
request, and the evaluation datasets planned for the evaluation module.
