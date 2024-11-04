# Other models

To configure the use of other models these are the usual steps, with examples for Anthropic and Gemini:

1. you need to create a Brevia project, see [Setup](../setup.md#create-a-brevia-project) for more details
1. you need to install the LangChain library that provides the model you want to use, for Anthropic see [here](https://python.langchain.com/docs/integrations/chat/anthropic/), for Gemini see [here](https://python.langchain.com/docs/integrations/chat/google_generative_ai/)
    1. for Anthropic you can install the library with `poetry add langchain-anthropic` or `pip install langchain-anthropic`
    1. for Gemini you can install the library with `poetry add langchain-google-genai` or `pip install langchain-google-genai`
1. you will probably need a token or API key from the service, made available as an environment variable, optionally using [`BREVIA_ENV_SECRETS`](../config.md#brevia-env-secrets) configuration
    1. for Anthropic you will need the `ANTHROPIC_API_KEY` environment variable, for Gemini the `GOOGLE_API_KEY` environment variable
1. you need to configure the desired model through a JSON object with key-value pairs, including `_type` with the fully qualified name of the LangChain integration class
    1. for Anthropic you can use [`langchain_anthropic.chat_models.ChatAnthropic`](https://python.langchain.com/api_reference/anthropic/chat_models/langchain_anthropic.chat_models.ChatAnthropic.html#langchain_anthropic.chat_models.ChatAnthropic) for chat models - Anthropic does not provide embeddings for now
    1. for Gemini you can use [`langchain_google_genai.chat_models.ChatGoogleGenerativeAI`](https://python.langchain.com/api_reference/google_genai/chat_models/langchain_google_genai.chat_models.ChatGoogleGenerativeAI.html) for chat models or [`langchain_google_genai.embeddings.GoogleGenerativeAIEmbeddings`](https://python.langchain.com/api_reference/google_genai/embeddings/langchain_google_genai.embeddings.GoogleGenerativeAIEmbeddings.html#langchain_google_genai.embeddings.GoogleGenerativeAIEmbeddings) for embeddings engine - look at the provided links for more details on the additional configuration options
