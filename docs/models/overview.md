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

- The APIs supported out of the box include **OpenAI, Cohere, and Ollama**. If using one of these services, no additional library installation is required. For other APIs, you'll need to install a library in your Brevia project. For example, see [Anthropic](https://python.langchain.com/docs/integrations/chat/anthropic/) or [Gemini](https://python.langchain.com/docs/integrations/chat/google_generative_ai/).

- Almost always, a token or API key from the service will be needed, made available as an environment variable; this is required for OpenAI and Cohere, but not for Ollama.

- The configuration of a specific model is handled through a JSON object with key-value pairs, including `_type` with the fully qualified name of the LangChain class responsible for interacting with the model.

Below, we will demonstrate how to configure the use of **[OpenAI](openai.md), [Cohere](cohere.md), and [Ollama](ollama.md)**, as well as **[examples for other models](other_models.md)**.
