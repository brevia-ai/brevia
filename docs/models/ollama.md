# Ollama integration

To configure the use of [Ollama](https://ollama.com) models you don't usually need a valid **API KEY** but you will have to specify:

* a base API URL if Ollama is not running on the same machine as Brevia.
* a model from the [Ollama model library](https://ollama.com/library)

## Embeddings

The basic configuration is as follows:

```bash
EMBEDDINGS='{"_type": "langchain_ollama.embeddings.OllamaEmbeddings" , "model": "nomic-embed-text"}'
```

Key variables you can add to this configuration include:

* `model`: the name of Ollama model to use (string)
* `base_url`: base url the model is hosted under, defaults to `http://127.0.0.1:11434`

For additional configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/ollama/embeddings/langchain_ollama.embeddings.OllamaEmbeddings.html#langchain_ollama.embeddings.OllamaEmbeddings).

## Conversational LLM

Conversational LLMs are configured using the variables [`QA_COMPLETION_LLM` and `QA_FOLLOWUP_LLM`](../config.md#qa-and-chat) or [`SUMMARIZE_LLM` for summarization and analysis](../config.md#summarization) that use the same JSON format.

An example JSON configuration using Meta's Llama 3.2 might look like this:

```json
{"model": "llama3.2", "model_provider": "ollama", "base_url":"http://localhost:11434", "temperature": 0}
```

The primary variables you can add to this configuration include:

* `model`: name of the Ollama model to use (string)
* `base_url`: base url the model is hosted under, defaults to `http://127.0.0.1:11434`
* `temperature`: sampling temperature, ranges from 0.0 to 1.0. (float)
* `num_predict`: max number of tokens to generate (int)

See [here](overview.md#model-configuration-formats) for more details on the configuration format.

For further configuration options, refer to the [LangChain API reference](https://python.langchain.com/api_reference/ollama/chat_models/langchain_ollama.chat_models.ChatOllama.html#langchain_ollama.chat_models.ChatOllama).
