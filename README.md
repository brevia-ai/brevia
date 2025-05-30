# Brevia

[![Github Actions CS](https://github.com/brevia-ai/brevia/actions/workflows/cs.yml/badge.svg)](https://github.com/brevia-ai/brevia/actions?query=workflow%3Acs)
[![Github Actions Unit](https://github.com/brevia-ai/brevia/actions/workflows/unit.yml/badge.svg)](https://github.com/brevia-ai/brevia/actions?query=workflow%3Aunit)
[![Coverage Status](https://coveralls.io/repos/github/brevia-ai/brevia/badge.svg?branch=main&kill_cache=1)](https://coveralls.io/github/brevia-ai/brevia?branch=main)
![Python Versions](https://img.shields.io/pypi/pyversions/brevia.svg)
[![Version](https://img.shields.io/pypi/v/brevia.svg?label=brevia)](https://pypi.org/project/brevia/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](https://github.com/brevia-ai/brevia/blob/main/LICENSE)

Brevia is an extensible API and framework to build your Retrieval Augmented Generation (RAG) and Information Extraction (IE) applications with LLMs.

Ouf of the box Brevia provides:

* a complete API for RAG applications
* an API with Information extractions capabilities like summarization, with the possibility to create your own analysis logic with asycnhronous background operations support

Brevia uses:

* the popular [LangChain](https://github.com/langchain-ai/langchain) framework that you can use to create your custom AI tools and logic
* the [FastAPI](https://github.com/tiangolo/fastapi) framework to easily extend your application with new endpoints
* [PostgreSQL](https://www.postgresql.org) with [`pg_vector`](https://github.com/pgvector/pgvector) extension as vector database

## Documentation

Brevia documentation is available at [docs.brevia.app](https://docs.brevia.app).

## Admin UI

An official UI is now available via [Brevia App](https://github.com/brevia-ai/brevia-app).
It is a webapp with which you can:

* create and configure new RAG collections
* add files, questions or links to each collection
* test the collection with a chat UI
* analyze the chat history for each collection
* perform some Information Extraction actions like summarization, audio transcription or custom analysis

## Requirements

A version of Python 3.10 or higher and [Poetry](https://python-poetry.org/docs/#installation) is required.
A PostgreSQL database version 14 or higher with [`pg_vector`](https://github.com/pgvector/pgvector), but you can use the provided docker image for a quicker setup.

## Quick try

The easiest and fastest way to try Brevia is through Docker. By launching docker compose with the following command you will have a working Brevia system without any setup or configuration:

```bash
# download docker-compose.yml and .env files - not necessary if you are in the brevia repo
curl -o docker-compose.yml https://raw.githubusercontent.com/brevia-ai/brevia/refs/heads/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/brevia-ai/brevia/refs/heads/main/.env.sample

docker compose --profile fullstack up
```

At this point you will have:

* Brevia API on http://localhost:8000
* Brevia App UI on http://localhost:3000
* [PgAdmin UI](https://www.pgadmin.org) on http://localhost:4000
* [PostgreSQL](https://www.postgresql.org) with [`pg_vector`](https://github.com/pgvector/pgvector) extension running on `localhost:5432`

To use ports other than 8000, 3000, 4000 or 5432 you may use the environment variables `BREVIA_API_PORT`, `BREVIA_APP_PORT`, `PGVECTOR_PORT` or `PGADMIN_PORT` either in the .env file or setting them before the `docker compose up` command.

You can also use `--profile api` option to just start Brevia API and not Brevia App.

## Create a Brevia Project

### Quick start

The quickest way to create a new Brevia project is using the [cookiecutter](https://github.com/cookiecutter/cookiecutter) template project like this:

```bash
pip install cookiecutter
cookiecutter gh:brevia-ai/brevia-cookiecutter
```

Simply answer few simple questions and you're ready to go.

### Manual setup

To manually create a project instead follow these steps:

* create a new project with `poetry new {your-brevia-project}`
* install brevia and its dependencies by running `poetry add brevia`, a virtualenv will automatically be created
* create a new `main.py` starting with a [copy](https://raw.githubusercontent.com/brevia-ai/brevia-cookiecutter/main/%7B%7Bcookiecutter.project_slug%7D%7D/main.py)
* activate the virtualenv by running the `poetry env activate` command
* copy the file `.env.sample` to `.env` and value the environment variables, especially secrets like API keys for LLM API services (e.g. `OPENAI_API_KEY` for OpenAI or `COHERE_API_KEY` for Cohere) and database connection via `PGVECTOR_*`.  see the [Database](#database) section

## Model configuration

With Brevia you can configure any Large Language Model supported by LangChain, virtually all major models currently available.
Please have a look at the model configuration in the [Brevia documentation](https://docs.brevia.app/models/overview/) for more details.
Follow the steps below to set up and use a custom model in your Brevia project.

### Ollama Model Integration

Suppose you want to use a local Llama 3.2 model via [Ollama](https://ollama.com) you can update your Brevia project like this:

1. Open the `.env` file in your project directory.

2. For QA/RAG application, set in `QA_COMPLETION_LLM` and `QA_FOLLOWUP_LLM` the json as follow:

```bash
QA_COMPLETION_LLM='{
    "model_provider": "ollama",
    "model": "llama3.2",
    "temperature": 0,
    "max_tokens": 1000
}'
QA_FOLLOWUP_LLM='{
    "model_provider": "ollama",
    "model": "llama3.2",
    "temperature": 0,
    "max_tokens": 200
}'
```

3. You may want to configure the embeddings engine as well, in this case you can use another model like `nomic-embed-text` this way:

```bash
EMBEDDINGS='{
    "_type": "langchain_ollama.embeddings.OllamaEmbeddings",
    "model": "nomic-embed-text"
}'
```

4. For the summarization functions, you can set the `SUMMARIZE_LLM` var:

```bash
SUMMARIZE_LLM='{
    "model_provider": "ollama",
    "model": "llama3.2",
    "temperature": 0,
    "max_tokens": 2000
}'
```

## Database

If you have a PostgreSQL instance with `pg_vector` extension available you are ready to go, otherwise you can use the provided docker compose file.

In this case you can simply run `docker compose` to run a PostgreSQL database with pg_vector.
You can also run the embedded [`pgAdmin`](https://www.pgadmin.org) admin tool running `docker compose --profile admin up` to run postgres+pgvector and pgadmin docker images at the same time.
With your browser, open `pgadmin` at http://localhost:4000

The `4000` port is configurable with the `PGADMIN_PORT` environment var in the `.env` file.

## Migrations

Before using Brevia you need to launch the migrations script in order to create or update the initial schema. This is done with [Alembic](https://alembic.sqlalchemy.org) by using this command

```bash
db_upgrade
```

## Launch

You are now ready to go, simply run

```bash
uvicorn --env-file .env main:app`
```

and your [Brevia API](https://github.com/brevia-ai/brevia) project is ready to accept calls!

## Test your API

While we are working on a simple reference frontend to test and use Brevia API the simplest way to test your new API is by using the provided OpenAPI Swagger UI and ReDoc UI or by using the official Postman files.

Simply point to `/docs` for your Swagger UI and to `/redoc` for ReDoc.

If you prefer to use Postman you can start by importing the [collection file](https://raw.githubusercontent.com/brevia-ai/brevia/main/brevia/postman/Brevia%20API.postman_collection.json) and an [environment sample](https://raw.githubusercontent.com/brevia-ai/brevia/main/brevia/postman/Brevia%20API.postman_environment.json)

## Add documents via CLI

You can also quickly create collections and add documents via CLI using the `import_file` command.

Just run:

```bash
import_file --file-path /path/to/file --collection my-collection
```

Where

* `/path/to/file` is the path to a local PDF or txt file
* `my-collection` is the unique name of the collection that will be created if not exists

## Import/export of collections

To import/export collections via CLI we take advantage of the [PostgreSQL COPY command](https://www.postgresql.org/docs/current/sql-copy.html) in the `import_collection` and `export_collection` scripts.

A `psql` client is required for these scripts, connection parameters will be read from environment variables (via `.env` file).

Two PostgreSQL CSV files will be created during export and imported in the import operation.
One file, named `{collection-name}-collection.csv`, contains collection data and the other, named `{collection-name}-embedding.csv`, contains documents data and embeddings.

To export a collection use:

```bash
export_collection --folder-path /path/to/folder --collection collection-name
```

To import a collection use:

```bash
import_collection --folder-path /path/to/folder --collection collection-name
```

Where

* `/path/to/folder` is the path where the 2 CSV files will be created in export or searched in import
* `collection-name` is the name of the collection

## LangSmith support

[LangSmith](https://www.langchain.com/langsmith) is a platform to monitor, test and debug LLM apps built with LangChain.
To use it in Brevia, if you have an account, you should export these environment variables when runnnin Brevia:

```bash
LANGCHAIN_TRACING_V2=True
LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
LANGCHAIN_API_KEY="########"
LANGCHAIN_PROJECT="My Project"
```

If you are using a `.env` file you should use `BREVIA_ENV_SECRETS` var like this:

```bash

BREVIA_ENV_SECRETS='{
  "LANGCHAIN_TRACING_V2": "True"
  "LANGCHAIN_ENDPOINT": "https://api.smith.langchain.com",
  "LANGCHAIN_API_KEY": "########",
  "LANGCHAIN_PROJECT": "My Project"
}'
```

This way Brevia will make sure that this variables will be available as environment variables.

Edit `LANGCHAIN_API_KEY` with your LangSmith API Key and set your project name in `LANGCHAIN_PROJECT` var.

## Access Tokens

There is a built-in basic support for access tokens for API security.

Access tokens are actively checked via `Authoritazion: Bearer <token>` header if a `TOKENS_SECRET` env variable has been set.
You may then generate a new access token using:

```bash
poetry run create_token --user {user} --duration {minutes}
```

If the env `TOKENS_SECRET` variable is set token verification is automatically performed on every endpoint using `brevia.dependencies.get_dependencies` in its dependencies.

The recommended way yo generate `TOKENS_SECRET` is by using openssl via cli like

```bash
openssl rand -hex 32
```

You can also define a list of valid users as a comma separated string in the `TOKENS_USERS` env variable.

Setting it like `TOKENS_USERS="brevia,gustavo"` means that only `brevia` and `gustavo` are considered valid users names. Remember to use double quotes in a `.env` file.

## Brevia developer quick reference

Here some brief notes if you want to help develop Brevia.

### Unit tests

To launch unit tests make sure to have `dev` dependencies installed. This is done with:

```bash
poetry install --with dev
```

A `tests/.env` file must be present where test environment variables are set, you can start with a copy of `tests/.env.sample`.
Please make sure that `PGVECTOR_*` variables point to a unit test database that will be continuously dropped and recreated. Also make sure to set `USE_TEST_MODELS=True` in order to use fake LLM instances.

To launch unit tests, type from virtualenv:

```bash
pytest tests/
```

To create coverage in HTML format:

```bash
pytest --cov-report html --cov=brevia tests/
```

Covreage report is created using `pytest-cov`

### Update documentation

Install `mkdocs-material` using `pip` without altering `pyproject.toml`

```bash
pip install mkdocs-material
```

When working on documentation files you can use a live preview server with:

```bash
mkdocs serve
```

Or you can build the documentation in `site/` folder using

```bash
mkdocs build --clean
```
