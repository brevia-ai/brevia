# Other models

To configure the use of other models these are the usual steps, with examples for Google Gemini:

1. you need to create a Brevia project, see [Setup](../setup.md#create-a-brevia-project) for more details
1. you need to install the LangChain library that provides the model you want to use, for Gemini see [here](https://python.langchain.com/docs/integrations/chat/google_generative_ai/)
    1. for Gemini you can install the library with `poetry add langchain-google-genai` or `pip install langchain-google-genai`
1. you will probably need a token or API key from the service, made available as an environment variable, optionally using [`BREVIA_ENV_SECRETS`](../config.md#brevia-env-secrets) configuration
    1. for Gemini the `GOOGLE_API_KEY` environment variable
1. you need to configure the desired model through a JSON object with key-value pairs as described in the [Model Configuration formats](overview.md#model-configuration-formats) section
    1. for Gemini you can use `google_genai` as `model_provider`, have a look at the [`ChatGoogleGenerativeAI` class](https://python.langchain.com/api_reference/google_genai/chat_models/langchain_google_genai.chat_models.ChatGoogleGenerativeAI.html) for other chat model parameters; you can also use [`langchain_google_genai.embeddings.GoogleGenerativeAIEmbeddings`](https://python.langchain.com/api_reference/google_genai/embeddings/langchain_google_genai.embeddings.GoogleGenerativeAIEmbeddings.html#langchain_google_genai.embeddings.GoogleGenerativeAIEmbeddings) for the embeddings engine - look at the provided links for more details on the additional configuration options
