# Executable analysis example

From a checkout, with a migrated development database configured in `.env`:

```sh
BREVIA_PROJECT_FILE=examples/analysis.toml uv run python examples/analysis_pipeline.py
```

The example is `examples/analysis_pipeline.py` in the repository, with its project
file `examples/analysis.toml`. It uses `fake_model` and calls no provider; it still
writes seven direct run records to the configured database. The unit suite executes
its activities (`register` and `run_examples`) with the in-memory store; the command
above, which also creates Brevia from the settings, is not part of the tests. Synthetic results demonstrate the API, not extraction quality.

| Activity | Demonstrates | Result |
|---|---|---|
| `example.generate` | Typed `generate`, explicit prompts, tool selection | `Summary` |
| `example.map_reduce` | `Document.from_text`, `split`, partials and combination | `Summary` |
| `example.refine` | Updating a summary over successive pieces | `Summary` |
| `example.summarize` | Ready activity with text input | `Summary` |
| `example.summarize_document` | Summarizing an already-read document | `Summary` |
| `example.extract` | Extraction into the project's `Invoice` schema | `Invoice` |
| `example.extract_document` | Extracting from an already-read document | `Invoice` |

Each activity registers its own prompt set. The names are distinct
(`summarize_refine` in `SUMMARIZE_PROMPTS`, `extract_refine` in `EXTRACT_PROMPTS`), so
one activity can declare both sets. Optional project rules added to every call are the
prompts `summarize_rules` and `extract_rules`; see [Analysis](analysis.md).

## Parameters and failures

- `generate`: `instructions`, `user_text`, `output_type`; optional `validator`,
  `max_attempts`, `max_output_tokens`, `tools`. A validator returns problems for the
  model to correct. The example uses scripted final outputs, so its selected tool is
  not executed; [tool tests](tools.md#records-and-tests) cover tool execution.
- `split(document, max_chars)`: positive character limit, no overlap. Whole sections
  stay together when possible; long sections are cut at paragraphs or by size.
  `Piece.start` and `end` identify source sections. See [Documents](documents.md).
- `map_reduce`: pieces, `output_type`, `map_prompt`, `combine_prompt`, optional
  `partial_type`, `values`, `rules`, `validator`, `max_chars`, model and generation
  limits.
  Groups must fit the size; if no pair can fit, it raises `LimitExceeded`.
- `refine`: pieces, `output_type`, `first_prompt`, `refine_prompt` (with `{previous}`),
  optional values, `rules`, validator, model and generation limits. A validator sees every
  partial result. Long lists may still lose items: schema validity is not completeness.
- `summarize`: text or file, optional language; configuration selects model, language,
  strategy, input size and output tokens. It reads, splits if needed and combines.
- `extract`: text or file, project's output type and optional validator;
  configuration selects model, sizes and attempts. Long documents use refine.
- `summarize_document` and `extract_document`: accept an already-read `Document`
  instead of reading a source again; the activity must still declare their prompts.

The reference gives every default and signature. Wrong sources or empty text raise
`InvalidInput`; missing prompts `NotFound`; unreadable formats `Unsupported`.
Model calls can raise `OutputInvalid`, `LimitExceeded`, `RunTimeout`, `ProviderError`
or `Unavailable`. Corrections consume the same run budget as successful requests.
For the algorithms and diagrams see [Pipelines](pipelines.md); for registration,
file input, configuration and prompt customization see [Analysis](analysis.md).
