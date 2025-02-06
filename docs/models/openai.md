# OpenAI integration

To configure the use of OpenAI models, you need a valid **API KEY**, which must be available in Brevia as the `OPENAI_API_KEY` environment variable. One way to set this is by using the `BREVIA_ENV_SECRETS` configuration in the `.env` file, as described [here](../config.md#brevia-env-secrets).

## Embeddings

The basic configuration is as follows:

```bash
EMBEDDINGS='{"_type": "openai-embeddings"}'
```

where `openai-embeddings` serves as an alias for `langchain_openai.embeddings.OpenAIEmbeddings`, which can be used interchangeably.

Key variables you can add to this configuration include:

- `model`: the name of the OpenAI model to use (string)
- `dimensions`: output embeddings size, supported only for `text-embedding-3` and later models.

For additional configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/openai/embeddings/langchain_openai.embeddings.base.OpenAIEmbeddings.html).

## Conversational LLM

Conversational LLMs are configured using the variables [`QA_COMPLETION_LLM` and `QA_FOLLOWUP_LLM`](../config.md#qa-and-chat) or [`SUMMARIZE_LLM` for summarization and analysis](../config.md#summarization) that use the same JSON format.

An example JSON configuration might look like this:

```json
{"model": "gpt-4o-mini", "model_provider": "openai", "temperature": 0, "max_tokens": 1000}
```

The primary variables you can add to this configuration include:

- `model`: name of the OpenAI model to use (string)
- `temperature`: sampling temperature (float, between 0 and 1)
- `max_tokens`: maximum number of tokens to generate (int)

See [here](../config.md#model-configuration-formats) for more details on the configuration format.

For further configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/openai/chat_models/langchain_openai.chat_models.base.ChatOpenAI.html#langchain_openai.chat_models.base.ChatOpenAI).
