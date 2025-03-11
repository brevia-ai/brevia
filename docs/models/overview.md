# Working with Models

**Brevia API** has been designed to avoid dependency on a single AI model, enabling easy integration with the leading AI models currently available, as well as future models.

These models are accessed through **LangChain**, a library that offers extensive, continuously updated support.

The types of interactions with LLMs currently supported by Brevia are as follows:

1. Embedding engine for indexed content and conversation
2. Conversational LLM for the model's final response
3. Conversational LLM for generating follow-up questions within a conversation
4. Information extraction for summarization and other types of analysis

The first three interactions are used in RAG/Chat/Q&A applications.

For each of these interactions, configurations can be set to use a specific LLM as the default or for individual collections in RAG applications (see the first three points above).

Custom configurations can also be applied on a case-by-case basis for specific information extraction tasks, even using agents.

## Key Points for Integrating a Specific Model

- The APIs supported out of the box include **OpenAI, Cohere, Anthropic, DeepSeek and Ollama**. If using one of these services, no additional library installation is required. For other APIs, you'll need to install a library in your Brevia project. For example, see [Gemini](https://python.langchain.com/docs/integrations/chat/google_generative_ai/).

- Almost always, a token or API key from the service will be needed, made available as an environment variable; this is required for OpenAI, Cohere, Anthropic and DeepSeek but not for Ollama.

- The configuration of a specific model is handled through a JSON object with key-value pairs; two possible formats are supported, explained below.

## Model Configuration formats

The recommended format includes the following keys:

- `model` – (required) The name of the model to use.
- `model_provider` – (required) The name of the provider of the model.
- `temperature` – (optional) The sampling temperature for the model.
- `max_tokens` – (optional) The maximum number of tokens to generate in the model's response.
- `timeout` – (optional) The maximum time in seconds to wait for a response from the model.
- `base_url` – (optional) The base URL for the API endpoint of the model.
- `max_retries` – (optional) The maximum number of attempts the system will make to resend a request if it fails due to issues like network timeouts or rate limits.

For example:

```json
{"model": "gpt-4o-mini", "model_provider": "openai", "temperature": 0, "max_tokens": 1000, "timeout": 60, "max_retries": 3, "base_url": "https://api.openai.com/v1"}
```

Other keys can be added as needed, depending on the model and the specific requirements of the interaction.

Alternatively you can explicitly specify the ChatModel class using `_type` with the fully qualified name of the LangChain class responsible for interacting with the model and other keys like `model`, `temperature`, `max_tokens`, etc. For example:

```json
{"_type": "langchain_openai.chat_models.base.ChatOpenAI", "model": "gpt-4o-mini", "temperature": 0, "max_tokens": 1000}
```

In the next paragraphs we will demonstrate how to configure the use of **[OpenAI](openai.md), [Cohere](cohere.md), [Ollama](ollama.md), [Anthropic](anthropic.md) and [DeepSeek](deepseek.md)**, as well as **[examples for other models](other_models.md)**.
