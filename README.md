# Brevia

[![Github Actions CS](https://github.com/brevia-ai/brevia/actions/workflows/cs.yml/badge.svg)](https://github.com/brevia-ai/brevia/actions?query=workflow%3Acs)
[![Github Actions Unit](https://github.com/brevia-ai/brevia/actions/workflows/unit.yml/badge.svg)](https://github.com/brevia-ai/brevia/actions?query=workflow%3Aunit)
[![Coverage Status](https://coveralls.io/repos/github/brevia-ai/brevia/badge.svg?branch=main&kill_cache=1)](https://coveralls.io/github/brevia-ai/brevia?branch=main)
![Python Versions](https://img.shields.io/pypi/pyversions/brevia.svg)
[![Version](https://img.shields.io/pypi/v/brevia.svg?label=brevia)](https://pypi.org/project/brevia/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](https://github.com/brevia-ai/brevia/blob/main/LICENSE)

Brevia is an extensible API and framework for building Retrieval Augmented Generation (RAG) and Information Extraction (IE) applications with LLMs.

Out of the box, Brevia provides:

* A complete API for RAG applications
* An API with information extraction capabilities such as summarization, with the ability to create your own analysis logic and support for asynchronous background operations

Brevia uses:

* The popular [LangChain](https://github.com/langchain-ai/langchain) framework, which you can use to create custom AI tools and logic
* The [FastAPI](https://github.com/tiangolo/fastapi) framework to easily extend your application with new endpoints
* [PostgreSQL](https://www.postgresql.org) with the [`pg_vector`](https://github.com/pgvector/pgvector) extension as a vector database

## Documentation

Brevia documentation is available at [docs.brevia.app](https://docs.brevia.app).

## Admin UI

An official UI is now available via [Brevia App](https://github.com/brevia-ai/brevia-app).
It is a web app that allows you to:

* Create and configure new RAG collections
* Add files, questions, or links to each collection
* Test collections with a chat UI
* Analyze the chat history for each collection
* Perform information extraction actions such as summarization, audio transcription, or custom analysis

## Requirements

You need Python 3.10 or higher and [Poetry](https://python-poetry.org/docs/#installation).
A PostgreSQL database version 14 or higher with [`pg_vector`](https://github.com/pgvector/pgvector) is required, but you can use the provided Docker image for a quick setup.

## Quick Try

The easiest way to try Brevia is through Docker. By launching Docker Compose with the following command, you will have a working Brevia system without any setup or configuration:

```bash
# Download docker-compose.yml and .env files (not necessary if you are in the brevia repo)
curl -o docker-compose.yml https://raw.githubusercontent.com/brevia-ai/brevia/refs/heads/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/brevia-ai/brevia/refs/heads/main/.env.sample

docker compose --profile fullstack up
```

This will provide:

* Brevia API at http://localhost:8000
* Brevia App UI at http://localhost:3000
* [PgAdmin UI](https://www.pgadmin.org) at http://localhost:4000
* [PostgreSQL](https://www.postgresql.org) with [`pg_vector`](https://github.com/pgvector/pgvector) running on `localhost:5432`

To use ports other than 8000, 3000, 4000, or 5432, set the environment variables `BREVIA_API_PORT`, `BREVIA_APP_PORT`, `PGVECTOR_PORT`, or `PGADMIN_PORT` in the `.env` file or before running the Docker compose command.

You can also use:

* `--profile api` option to start only the Brevia API without the Brevia App
* `--profile admin` option to start only the Postgres+pg_vector and the PgAdmin UI.

Without any `--profile` option, only the Postgres+pg_vector service will start.

## Create a Brevia Project

### Quick Start

The fastest way to create a new Brevia project is by using the [cookiecutter](https://github.com/cookiecutter/cookiecutter) template:

```bash
pip install cookiecutter
cookiecutter gh:brevia-ai/brevia-cookiecutter
```

Simply answer a few questions and you're ready to go.

### Manual Setup

To set up a project manually:

* Create a new project with `poetry new {your-brevia-project}`
* Install Brevia and its dependencies by running `poetry add brevia` (a virtualenv will be created automatically)
* Create a new `main.py` starting with a [copy](https://raw.githubusercontent.com/brevia-ai/brevia-cookiecutter/main/%7B%7Bcookiecutter.project_slug%7D%7D/main.py)
* Activate the virtualenv by running `poetry env activate`
* Copy `.env.sample` to `.env` and set the environment variables, especially secrets like API keys for LLM API services (e.g., `OPENAI_API_KEY` for OpenAI or `COHERE_API_KEY` for Cohere) and database connection via `PGVECTOR_*`. See the [Database](#database) section.

## Model Configuration

With Brevia, you can configure any Large Language Model supported by LangChain—virtually all major models currently available.
See the [Brevia documentation](https://docs.brevia.app/models/overview/) for more details.
Follow the steps below to set up and use a custom model in your Brevia project.

### Ollama Model Integration

Suppose you want to use a local Llama 3.2 model via [Ollama](https://ollama.com). Update your Brevia project as follows:

1. Open the `.env` file in your project directory.

2. For QA/RAG applications, set `QA_COMPLETION_LLM` and `QA_FOLLOWUP_LLM` as follows:

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

3. To configure the embeddings engine, you can use another model such as `nomic-embed-text`:

```bash
EMBEDDINGS='{
    "_type": "langchain_ollama.embeddings.OllamaEmbeddings",
    "model": "nomic-embed-text"
}'
```

4. For summarization functions, set the `SUMMARIZE_LLM` variable:

```bash
SUMMARIZE_LLM='{
    "model_provider": "ollama",
    "model": "llama3.2",
    "temperature": 0,
    "max_tokens": 2000
}'
```

## Database

If you have a PostgreSQL instance with the `pg_vector` extension available, you are ready to go. Otherwise, you can use the provided Docker Compose file.

Simply run `docker compose up` to start a PostgreSQL database with `pg_vector`.
You can also run the embedded [`pgAdmin`](https://www.pgadmin.org) admin tool by running `docker compose --profile admin up` to start both the postgres+pgvector and pgadmin Docker images.
Open `pgadmin` in your browser at http://localhost:4000

The `4000` port is configurable via the `PGADMIN_PORT` environment variable in the `.env` file.

## Migrations

Before using Brevia, you need to run the migrations script to create or update the initial schema. Use the following command from the virtual environment:

```bash
db_upgrade
```

This will run migrations using [Alembic](https://alembic.sqlalchemy.org/en/latest/) (already installed as a dependency) to create or update the required tables in your database.

## Launch

You are now ready to go. Simply run from the virtual environment:

```bash
uvicorn --env-file .env main:app
```

and your [Brevia API](https://github.com/brevia-ai/brevia) project is ready to accept calls!

## Test Your API

While we are working on a simple reference frontend for Brevia API, the easiest way to test your new API is by using the provided OpenAPI Swagger UI and ReDoc UI, or by using the official Postman files.

Go to `/docs` for Swagger UI and `/redoc` for ReDoc.

If you prefer Postman, you can import the [collection file](https://raw.githubusercontent.com/brevia-ai/brevia/main/brevia/postman/Brevia%20API.postman_collection.json) and an [environment sample](https://raw.githubusercontent.com/brevia-ai/brevia/main/brevia/postman/Brevia%20API.postman_environment.json).

## Add Documents via CLI

You can quickly create collections and add documents via CLI using the `import_file` command:

```bash
import_file --file-path /path/to/file --collection my-collection
```

Where:

* `/path/to/file` is the path to a local PDF or TXT file
* `my-collection` is the unique name of the collection (it will be created if it does not exist)

## Import/Export Collections

To import or export collections via CLI, use the [PostgreSQL COPY command](https://www.postgresql.org/docs/current/sql-copy.html) in the `import_collection` and `export_collection` scripts.

A `psql` client is required for these scripts. Connection parameters are read from environment variables (via the `.env` file).

Two PostgreSQL CSV files will be created during export and imported during import:
* `{collection-name}-collection.csv` contains collection data
* `{collection-name}-embedding.csv` contains document data and embeddings

To export a collection:

```bash
export_collection --folder-path /path/to/folder --collection collection-name
```

To import a collection:

```bash
import_collection --folder-path /path/to/folder --collection collection-name
```

Where:

* `/path/to/folder` is the path where the two CSV files will be created (export) or searched for (import)
* `collection-name` is the name of the collection

## LangSmith Support

[LangSmith](https://www.langchain.com/langsmith) is a platform to monitor, test, and debug LLM apps built with LangChain.
To use it in Brevia, if you have an account, export these environment variables when running Brevia:

```bash
LANGCHAIN_TRACING_V2=True
LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
LANGCHAIN_API_KEY="########"
LANGCHAIN_PROJECT="My Project"
```

If you are using a `.env` file, use the `BREVIA_ENV_SECRETS` variable like this:

```bash
BREVIA_ENV_SECRETS='{
  "LANGCHAIN_TRACING_V2": "True",
  "LANGCHAIN_ENDPOINT": "https://api.smith.langchain.com",
  "LANGCHAIN_API_KEY": "########",
  "LANGCHAIN_PROJECT": "My Project"
}'
```

This ensures these variables are available as environment variables.

Edit `LANGCHAIN_API_KEY` with your LangSmith API Key and set your project name in the `LANGCHAIN_PROJECT` variable.

## Access Tokens

There is basic built-in support for access tokens for API security.

Access tokens are checked via the `Authorization: Bearer <token>` header if the `TOKENS_SECRET` environment variable is set.
You can generate a new access token using:

```bash
poetry run create_token --user {user} --duration {minutes}
```

If the `TOKENS_SECRET` environment variable is set, token verification is automatically performed on every endpoint using `brevia.dependencies.get_dependencies`.

The recommended way to generate `TOKENS_SECRET` is with openssl:

```bash
openssl rand -hex 32
```

You can also define a list of valid users as a comma-separated string in the `TOKENS_USERS` environment variable.

For example, setting `TOKENS_USERS="brevia,gustavo"` means that only `brevia` and `gustavo` are considered valid user names. Remember to use double quotes in a `.env` file.

## Brevia Developer Quick Reference

Here are some brief notes if you want to help develop Brevia.

### Unit Tests

To run unit tests, make sure you have the `dev` dependencies installed:

```bash
poetry install --with dev
```

A `tests/.env` file must be present with test environment variables set. You can start with a copy of `tests/.env.sample`.
Ensure that `PGVECTOR_*` variables point to a unit test database that will be continuously dropped and recreated. Also, set `USE_TEST_MODELS=True` to use fake LLM instances.

To run unit tests from the virtualenv:

```bash
pytest tests/
```

To generate coverage in HTML format:

```bash
pytest --cov-report html --cov=brevia tests/
```

The coverage report is created using `pytest-cov`.

### Update Documentation

Install `mkdocs-material` using `pip` (do not alter `pyproject.toml`):

```bash
pip install mkdocs-material
```

When working on documentation files, you can use a live preview server with:

```bash
mkdocs serve
```

Or build the documentation in the `site/` folder using:

```bash
mkdocs build --clean
```
