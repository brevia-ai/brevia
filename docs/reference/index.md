# API reference

The Python API: what a project imports from `brevia`, the `brevia.analysis` module for
the analysis of documents, the `brevia.tools` module for tools of models, the
`brevia.config.defaults` module with the defaults of Brevia, the
`brevia.api` module for the HTTP application, and the `brevia.testing` module for
tests. Everything else in the package is internal.

| Page | Contents |
|---|---|
| [Application](application.md) | `Brevia`, `BreviaSettings`, `configure_logging` |
| [Runs and jobs](runs.md) | `RunContext`, `RunHandle`, `JobState`, `JobPage`, `FeedbackRequest`, `Correction`, `Feedback` |
| [Files](files.md) | `FileSource`, `FileRef`, `RunFiles`, `FileStore` |
| [Documents](documents.md) | `read_document`, `Document`, `Section`, `split`, `Piece` |
| [Analysis](analysis.md) | `map_reduce`, `refine`, `summarize`, `summarize_document`, `SummarizeRequest`, `SummarizeConfig`, `Summary`, `SUMMARIZE_PROMPTS`, `extract`, `extract_document`, `ExtractRequest`, `ExtractConfig`, `EXTRACT_PROMPTS` (module `brevia.analysis`) |
| [Access](access.md) | `Caller`, `AccessPolicy`, `Authenticator`, `AuthSettings`, `create_token` |
| [Configuration and prompts](customization.md) | `ConfigurationState`, `PromptState`, `PromptRevision`, `PromptTemplate` |
| [Models and limits](models.md) | `ModelClient`, `ModelSpec`, `ModelInfo`, `Prices`, `RunLimits`, `Validator` |
| [Defaults](defaults.md) | The defaults of Brevia (module `brevia.config.defaults`) |
| [HTTP API](api.md) | `brevia.api.create_app`, `BreviaDep`, `CallerDep` |
| [Errors](errors.md) | `BreviaError` and its subclasses |
| [Testing](testing.md) | `brevia.testing.fake_model` |

See also [Documents](documents.md), [Analysis](analysis.md) and [Tools](tools.md) for the stage 6 public API.
