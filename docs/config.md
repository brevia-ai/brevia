# Brevia Configuration

There are two type of configuration in a Brevia project:

* general configuration through environment variables or a simple `.env` file
* specific configuration of a single `collection` (mainly for RAG applications), stored as JSON in `langchain_pg_collection.cmetadata` database column

In this page we will explain the general configuration in Brevia.
All configuration items have working defaults exception of:

* external services settings like LLM APIs or monitor/debugging tools (Langsmith). Those services rely on specific environment variables that we cannot include or predict here.
* database connection configuration

In the following paragraphs we will detail all

## Database

These settings define the connection to your Postgres database with `pgvector` extension

* `PGVECTOR_DRIVER`: `psycopg2` default should be left unchanged, you may want to avoid this item in your configuration
* `PGVECTOR_HOST`: the database host name or address, `localhost` as default
* `PGVECTOR_PORT`: =5432
PGVECTOR_DATABASE=chatlas
PGVECTOR_USER=postgres
PGVECTOR_PASSWORD=postgres
PGVECTOR_POOLSIZE=25 -

## External services

As example of external services here we include OpenAI, Cohere and LangSmith

### OpenAI

### Cohere

### LangSmith

## Security

TOKENS_SECRET=asdacadfjaofsdohfwehfdoavhsbvhsdvfadhf
TOKENS_USERS="brevia,gustavo"
STATUS_TOKEN=abcdefgh

## Index and search

TEXT_CHUNK_SIZE=2000
TEXT_CHUNK_OVERLAP=100
EMBEDDINGS='{"_type": "openai-embeddings"}'
SEARCH_DOCS_NUM=6

## Q&A and Chat

QA_COMPLETION_LLM='{"_type": "openai-chat", "model_name": "gpt-3.5-turbo-16k", "temperature": 0, "max_tokens": 1000, "verbose": true}'
QA_FOLLOWUP_LLM='{"_type": "openai-chat", "model_name": "gpt-3.5-turbo-16k", "temperature": 0, "max_tokens": 200, "verbose": true}'
QA_FOLLOWUP_SIM_THRESHOLD=0.735
QA_NO_CHAT_HISTORY


## Summarization


SUMMARIZE_LLM='{"_type": "openai-chat", "model_name": "gpt-3.5-turbo-16k", "temperature": 0, "max_tokens": 2000}'
SUMM_TOKEN_SPLITTER=4000
SUMM_TOKEN_OVERLAP=500
SUMM_DEFAULT_CHAIN=stuff
