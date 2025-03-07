# DeepSeek integration

To configure the use of DeepSeek models, you need a valid **API KEY**, which must be available in Brevia as the `DEEPSEEK_API_KEY` environment variable. One way to set this is by using the `BREVIA_ENV_SECRETS` configuration in the `.env` file, as described [here](../config.md#brevia-env-secrets).

## Embeddings

DeepSeek currently does not offer any embeddings models.

## Conversational LLM

Conversational LLMs are configured using the variables [`QA_COMPLETION_LLM` and `QA_FOLLOWUP_LLM`](../config.md#qa-and-chat) or [`SUMMARIZE_LLM` for summarization and analysis](../config.md#summarization) that use the same JSON format.

An example JSON configuration might look like this:

```json
{"model": "deepseek-chat", "model_provider": "deepseek", "temperature": 1.0, "max_tokens": 1000}
```

The primary variables you can add to this configuration include:

- `model`: name of the DeepSeek model to use (string)
- `temperature`: sampling temperature (float, between 0 and 1.5)
- `max_tokens`: maximum number of tokens to generate (int)

See [here](overview.md#model-configuration-formats) for more details on the configuration format.

For further configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/deepseek/chat_models/langchain_deepseek.chat_models.ChatDeepSeek.html#langchain_deepseek.chat_models.ChatDeepSeek).
