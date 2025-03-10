# Brevia Configuration

There are two type of configuration in a Brevia project:

* general configuration set through environment variables or a simple `.env` file, [see below](#configuration-customization)
* specific configuration of a [single `collection`](collection_config.md) mainly for RAG applications, that are stored in the collection metadata

In this page we will explain the general configuration items in Brevia.

All configuration items have working defaults with the exception of:

* external services settings like LLM APIs or monitor/debugging tools (like Langsmith). Those services rely on specific environment variables that we cannot include or predict here
* database connection configuration

## Configuration customization

General configurations can be customized in various ways, some modes have precedence over others.

1. through a `.env` file in the app root folder
1. through environment variables
1. through the [`config` table records](database.md#schema) of the database

Each of the described modes prevails over the previouse ones in the order in which they are listed (DB configuration wins).

Database configuration can be done through [configuration endpoints](endpoints_overview.md#configuration-endpoints) but has some limitations: you cannot change some parameters such as the DB connection or security tokens.

## Database connection

These settings define the connection to your Postgres database with `pgvector` extension:

* `PGVECTOR_DRIVER`: `psycopg2` default should be left unchanged, you may want to avoid this item in your configuration
* `PGVECTOR_HOST`: the database host name or address, `localhost` as default
* `PGVECTOR_PORT`: the database connection port, `5432` as default
* `PGVECTOR_DATABASE`: the database name, `brevia` as default
* `PGVECTOR_USER`: database connection user, no default
* `PGVECTOR_PASSWORD`: database connection password, no default
* `PGVECTOR_POOL_SIZE`: connection pool size, `10` as default

If you prefer to define a single DSN URI for your connection you can use `PGVECTOR_DSN_URI` env variable. If this variable is set the `PGVECTOR_*` variables above will be ignored.
An example of such uri using Brevia defaults can look like `postgresql+psycopg2://user:password@localhost:5432/brevia`

## External services

As example of external services here we include OpenAI, Cohere, Anthropic, DeepSeek and LangSmith but it may include any LLM supported by LangChain. Those services usually need some specific env variables like API keys or tokens. If you don't set these variables, the services that depend on them may not work properly.

By using [`BREVIA_ENV_SECRETS` var as explained below](#brevia-env-secrets) you make sure that these secrets will be available as environment variables.

### Model providers

Brevia supports vistually any LLM provider, each with its own configuration. The following environment variables are necessary to configure them:

* to use OpenAI models via API you need to have a valid API KEY and define an `OPENAI_API_KEY` env var with its value. Please refer to [OpenAI model](models/openai.md) page for further details on using OpenAI.
* similarly to use Cohere model via API you need a valid API KEY that must be defined in `COHERE_API_KEY` env var. Have a look at [Cohere model](models/cohere.md) for more integration details.
* to use Anthropic models via API you need a valid API KEY that must be defined in `ANTHROPIC_API_KEY` env var. Have a look at [Anthropic model](models/anthropic.md) for more details.
* to use DeepSeek models via API you need a valid API KEY that must be defined in `DEEPSEEK_API_KEY` env var. Have a look at [DeepSeek model](models/deepseek.md) for more details.

### LangSmith

If you want to use [LangSmith](https://www.langchain.com/langsmith) to monitor your LLM application with Brevia you need to set these variables:

* `LANGCHAIN_TRACING_V2`: set to `True`, or any string actually
* `LANGCHAIN_ENDPOINT`: the endpoint used, like `https://api.smith.langchain.com`
* `LANGCHAIN_API_KEY`: your LangSmith API KEY
* `LANGCHAIN_PROJECT`: the name of your Brevia project

### Brevia env secrets

As mentioned above to make these variables available as environment variables, if not done explicitly outside Brevia, you can use a special JSON object variable `BREVIA_ENV_SECRETS` in your `.env` file where each key/value pair will be loaded in the environment at startup.

This variable could be something like `BREVIA_ENV_SECRETS='{"OPENAI_API_KEY": "#########", "COHERE_API_KEY": "#########"}'`

## Security

To enable a basic security support via tokens you may want to set the following variables:

* `TOKENS_SECRET`: the secret used when enconding and decoding tokens
* `TOKENS_USERS`: an optional comma separated list of valid user names that must be present in a token
* `STATUS_TOKEN`: a special token to be used only by the `/status` endpoint from 3rd party monitoring tools

Please check the [Security](security.md) section for more details on security support on Brevia.

## Index and search

This section focuses on the crucial components of indexing and searching for relevant information within your knowledge base.

### Embeddings

This variable specifies the type of embedding model used to convert text documents into numerical vectors. In this case, it's set to `openai-embeddings`, indicating that you'll be using OpenAI's embedding service.

`EMBEDDINGS='{"_type": "openai-embeddings"}'`

### Supported Embedding Services

`openai-embeddings`: Utilize OpenAI's embedding service for efficient conversion of text to numerical representations.

`cohere-embeddings`: Leverage Cohere's embedding service for alternative embedding calculations.

See [other models](models/other_models.md) for integrations with other 3rd party models

### Text Segmentation

`TEXT_CHUNK_SIZE`
This variable controls the maximum size of individual text chunks during processing. Large documents are split into smaller segments for efficient handling by the embedding model.

Default Value: 2000 (token)

Adjust this value based on your document sizes and hardware resources. Larger chunks typically yield more accurate embeddings, but require more memory. Experiment to find the optimal balance for your setup.

`TEXT_CHUNK_OVERLAP`
This variable specifies the amount of overlap between consecutive text chunks. Overlap ensures continuity within the document and helps capture contextual information across sections.

Default Value: 100 (token)

Increase the overlap for documents with important cross-sectional references, but reduce it for faster processing of independent sections.
Consider experimenting with different values based on your document characteristics.

example:

```bash
TEXT_CHUNK_SIZE=2000
TEXT_CHUNK_OVERLAP=100
```

`TEXT_SPLITTER`
This variable is an optional JSON string configuration, used to override the default text splitter

Can be something like:

`'{"splitter": "my_project.CustomSplitter", "some_var": "some_value"}'`

Where:

* `splitter` key must be present and point to a module path of a valid
   retriever class extending langchain `TextSplitter`
* other splitter constructor attributes can be specified in the configuration,
    like `some_var` in the above example

## Q&A and Chat

Under the hood of Q&A and Chat actions (see [Chat and Search](chat_search.md) section) you can configure models and behaviors via these variables:

* `QA_COMPLETION_LLM`: configuration for the main conversational model, used by `/chat` and `/completion` endpoints; a JSON string is used to configure the corresponding LangChain chat model class; an OpenAI instance is used as default: `'{"model_provider": "openai", "model": "gpt-4o-mini", "temperature": 0, "max_tokens": 2000}'` where for instance `model` and other attributes can be adjusted to meet your needs
* `QA_FOLLOWUP_LLM`: configuration for the follow-up question model, used by `/chat` endpoint defining a follow up question for a conversation usgin chat history; a JSON string; an OpenAI instance used as default `'{"model_provider": "openai", "model": "gpt-4o-mini", "temperature": 0, "max_tokens": 500}'`
* `QA_FOLLOWUP_SIM_THRESHOLD`: a numeric value between 0 and 1 indicating similarity threshold between questions to determine if chat history should be used, defaults to `0.735`
* `QA_NO_CHAT_HISTORY`: disables chat history entirely if set to `True` or any other value
* `SEARCH_DOCS_NUM`: default number of documents used to search for answers, defaults to `4`
* `QA_RETRIEVER`: optional configuration for a custom retriever class, used by `/chat`  endpoint, it's a JSON string defining a custom class and optional attributes; an example configuration can be `'{"retriever": "my_project.CustomRetriever", "some_var": "some_value"}'` where `retriever` key must be present with a module path pointing to a valid retriever class extending langchain `BaseRetriever` whereas other constructor attributes can be specified in the configuration, like `some_var` in the above example

## Summarization

To configure summarize related actions in `/summarize` or `/upload_summarize` endpoints the related environment variables are:

* `SUMMARIZE_LLM`: the LLM to be used, a JSON string using the same format of `QA_COMPLETION_LLM` in the above paragraph; defatults to an OpenAI instance `'{"model_provider": "openai", "model": "gpt-4o-mini" "temperature": 0, "max_tokens": 2000}'`
* `SUMM_TOKEN_SPLITTER`: the maximum size of individual text chunks processed during summarization, defaults to `4000` - see `TEXT_CHUNK_SIZE` in [Text Segmentation](#text-segmentation) paragraph
* `SUMM_TOKEN_OVERLAP`: the amount of overlap between consecutive text chunks, defaults to `500` - see `TEXT_CHUNK_OVERLAP` in [Text Segmentation](#text-segmentation) paragraph
* `SUMM_DEFAULT_CHAIN`: chain type to be used if not specified, defaults to `stuff`

## Providers

A list of supported providers and its models can be defined via `PROVIDERS` variable. This variable is a JSON string with the following format:

```JSON
[
    {
        "model_provider": "openai",
        "models": [
            {
                "name": "o1-mini"
            },
            {
                "name": "o3-mini"
            },
            {
                "name": "gpt-4o"
            },
            {
                "name": "gpt-4o-mini"
            }
        ]
    },
    {
        "model_provider": "cohere",
        "models": [
            {
                "name": "command-r",
                "tokens_limit": 128000
            },
            {
                "name": "command-r-plus",
                "tokens_limit": 128000
            }
        ]
    },
    {
        "model_provider": "anthropic",
        "models": [
            {
                "name": "claude-3-7-sonnet-20250219"
            },
            {
                "name": "claude-3-5-sonnet-20241022"
            }
        ]
    },
    {
        "model_provider": "ollama",
        "models": [
            {
                "name": "llama3.2:latest"
            }
        ]
    },
    {
        "model_provider": "deepseek",
        "models": [
            {
                "name": "deepseek-chat"
            },
            {
                "name": "deepseek-reasoner"
            }
        ]
    }
]
```

If not set this variable will be automatically populated with the current available providers and models at Brevia startup with the content of [the `/providers` endpoint response](endpoints_overview.md#providers-endpoints).
