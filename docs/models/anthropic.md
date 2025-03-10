# Anthropic integration

To configure the use of Anthropic models, you need a valid **API KEY**, which must be available in Brevia as the `ANTHROPIC_API_KEY` environment variable. One way to set this is by using the `BREVIA_ENV_SECRETS` configuration in the `.env` file, as described [here](../config.md#brevia-env-secrets).

## Embeddings

Anthropic currently does not offer any embeddings models.

## Conversational LLM

Conversational LLMs are configured using the variables [`QA_COMPLETION_LLM` and `QA_FOLLOWUP_LLM`](../config.md#qa-and-chat) or [`SUMMARIZE_LLM` for summarization and analysis](../config.md#summarization) that use the same JSON format.

An example JSON configuration might look like this:

```json
{"model": "claude-3-5-sonnet-latest", "model_provider": "anthropic", "temperature": 0}
```

The primary variables you can add to this configuration include:

- `model`: name of the Anthropic model to use (string)
- `temperature`: a non-negative float that tunes the degree of randomness in generation (float)

See [here](overview.md#model-configuration-formats) for more details on the configuration format.

For further configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/anthropic/chat_models/langchain_anthropic.chat_models.ChatAnthropic.html#langchain_anthropic.chat_models.ChatAnthropic).
