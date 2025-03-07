# Cohere integration

To configure the use of Cohere models, you need a valid **API KEY**, which must be available in Brevia as the `COHERE_API_KEY` environment variable. One way to set this is by using the `BREVIA_ENV_SECRETS` configuration in the `.env` file, as described [here](../config.md#brevia-env-secrets).

## Embeddings

The basic configuration is as follows:

```bash
EMBEDDINGS='{"_type": "langchain_cohere.embeddings.CohereEmbeddings" , "model": "embed-multilingual-v3.0"}'
```

Key variables you can add to this configuration include:

- `model`: the name of the Cohere model to use (string)

For additional configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/cohere/embeddings/langchain_cohere.embeddings.CohereEmbeddings.html#langchain_cohere.embeddings.CohereEmbeddings).

## Conversational LLM

Conversational LLMs are configured using the variables [`QA_COMPLETION_LLM` and `QA_FOLLOWUP_LLM`](../config.md#qa-and-chat) or [`SUMMARIZE_LLM` for summarization and analysis](../config.md#summarization) that use the same JSON format.

An example JSON configuration might look like this:

```json
{"model": "command-r-plus", "model_provider": "cohere", "temperature": 0}
```

The primary variables you can add to this configuration include:

- `model`: name of the Cohere model to use (string)
- `temperature`: a non-negative float that tunes the degree of randomness in generation (float)

See [here](overview.md#model-configuration-formats) for more details on the configuration format.

For further configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/openai/chat_models/langchain_openai.chat_models.base.ChatOpenAI.html#langchain_openai.chat_models.base.ChatOpenAI).
