# Prompts

Read this page to write the instructions an activity sends to a model, and to change
them without a release.

A prompt template is a text file with `{name}` placeholders, where `name` is a
lowercase identifier:

```text
Summarise the document in {language}.
Return JSON like {"summary": "..."}.
```

An activity declares the templates it uses when it is registered, with paths relative
to the directory of the project file:

```python
brevia.register_activity(..., prompts={"summary": "prompts/summary.md"})
```

and renders them through the run context:

```python
instructions = ctx.prompt("summary").render(language="English")
```

## Rules

- Templates have no loops, conditions or code: only substitution of declared
  placeholders.
- `render` requires exactly the variables of the template. Missing and unknown
  variables raise `InvalidInput`, with both lists in the details.
- Values are inserted as they are and never interpreted again as a template, so a
  value containing `{language}` stays literal.
- Braces that are not a placeholder, such as those of a JSON example, are left
  untouched.
- Prompt files are read once, at registration. Changing a file requires restarting the
  application; a [customisation](#customisation) changes a prompt without a release.
- There is no escape for a literal `{name}` with a lowercase name: such text is always
  a placeholder. Optional variables are not supported yet: every placeholder is
  required.

Every run records the text, the source (the file name, or `database`), the SHA-256
fingerprint and the customisation version (`null` for the file) of each template in
its [snapshot](runs.md#snapshots).

## Customisation

The text of a prompt can be replaced in the database for every new run, keeping the
file as its default. Like a [configuration customisation](configuration.md#customisation),
it is read when each run starts, or in the first step of a job. The operations are
methods of a started `Brevia`:

```python
state = await brevia.prompt("document.summarize", "summary")
state = await brevia.customize_prompt(
    "document.summarize",
    "summary",
    "Write a summary in {language}, in three sentences.",
    author="editor",
)
history = await brevia.prompt_history("document.summarize", "summary")
state = await brevia.reset_prompt("document.summarize", "summary")
```

- [`PromptState`](../reference/customization.md#brevia.PromptState) gives the file text, the
  customised text (`None` when the file is used), the effective text of a new run, the
  variables, the version and the author and time of the last change.
- A customised text must use **exactly** the variables of the file, so the code that
  renders the prompt keeps working.
- Each change, customisation or reset, is recorded in the history in the same
  transaction as the change. `prompt_history` returns the
  [`PromptRevision`](../reference/customization.md#brevia.PromptRevision) records, the most recent
  first: version, operation (`customize` or `reset`), text and fingerprint (`None` for
  a reset), author and time.
- `reset_prompt` returns to the file and keeps the history.
- `expected_version` detects concurrent changes as for the configuration (see
  [Concurrent changes](configuration.md#concurrent-changes)).
- Prompts cannot be replaced by a single request: instructions and request data stay
  separate.

### Restoring an earlier text

There is no separate restore operation: a restore is a new customisation with the text
of an earlier revision, and it is recorded in the history like any other change. For
example, after a customisation (version 1) and a reset (version 2):

```python
history = await brevia.prompt_history("document.summarize", "summary")
# [PromptRevision(version=2, operation="reset", text=None, ...),
#  PromptRevision(version=1, operation="customize", text="Write a summary...", ...)]
earlier = next(r for r in history if r.version == 1)
assert earlier.text is not None  # a customisation, not a reset
state = await brevia.prompt("document.summarize", "summary")
state = await brevia.customize_prompt(
    "document.summarize",
    "summary",
    earlier.text,
    expected_version=state.version,
    author="editor",
)
assert state.version == 3
assert state.effective == earlier.text
```

A revision with operation `reset` has no text: to return to the file, call
`reset_prompt`.

## When something goes wrong

| Situation | Error | What happens |
|---|---|---|
| `render` misses a variable or receives an unknown one | `InvalidInput` | The details list the missing and the unknown variables |
| A customised text has missing or extra variables, is blank or contains the NUL character (U+0000) | `InvalidInput` | Nothing is stored; the details list the variables |
| The activity or the prompt is not declared | `NotFound` | |
| `expected_version` is no longer current | `VersionConflict` | Nothing is changed: read the state again |
| A stored text no longer matches the variables of the file, after a release that changes them | `Unavailable` | Runs stop until the prompt is customised again or reset |
