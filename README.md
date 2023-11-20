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

* the popular LangChain library that you can use to create your custom AI tools and logic
* the FastAPI framework to easily extend your application with new endpoints
* PostgreSQL with [`pg_vector`](https://github.com/pgvector/pgvector) extension as vector database

## Requirements

A version of Python 3.10 or higher and [Poetry](https://python-poetry.org/docs/#installation) is required.
A PostgreSQL database version 11 or higher with [`pg_vector`](https://github.com/pgvector/pgvector), but you can use the provided docker image for a quicker setup.

## Quick start

The quickest way to try out Brevia is using the [cookiecutter](https://github.com/cookiecutter/cookiecutter) template project like this:

```bash
pip install cookiecutter
cookiecutter gh:brevia-ai/brevia-cookiecutter
```

Simply answer few simple questions and you're ready to go.

## Manual setup

To perform a manual setup follow these steps:

* create a new project with `poetry new {your-brevia-project}`
* install brevia and its dependencies by running `poetry add brevia`, a virtualenv will automatically be created
* create a new `main.py` starting with a [copy](https://raw.githubusercontent.com/brevia-ai/brevia-cookiecutter/main/%7B%7Bcookiecutter.project_slug%7D%7D/main.py)
* activate the virtualenv by running the `poetry shell` command
* copy the file `.env.sample` to `.env` and value the environment variables, especially `OPENAI_API_KEY` with the secret key of OpenAI and `PGVECTOR_*` see the [Database](#database) section

## Database

If you have a PostreSQL instance with `pg_vector` extension available you are ready to go, otherwise you can use the provided docker compose file.
In this case you can simply run `docker compose --profile admin up` to run postgres+pgvector and pgadmin docker images. With your browser, open `pgadmin` at http://localhost:4000

The `4000` port is configurable with the `PGADMIN_PORT` environment var in the `.env` file.

In this case you can simply run `docker compose --profile admin up` to run postgres+pgvector and pgadmin docker images. With your browser, open `pgadmin` at http://localhost:4000

The `4000` port is configurable with the `PGADMIN_PORT` environment var in the `.env` file.


Launch migrations to create the initial schema with [Alembic](https://alembic.sqlalchemy.org) by using this brevia command

```bash
db_upgrade
```

## Launch

You are now ready to go, simply run

```bash
uvicorn --env-file .env main:app`
```

and your [Brevia API](https://github.com/brevia-ai/brevia) project is ready to accept calls!

## Import/export of collections.

To export use the `export_collection.py` script from the virtual env

```bash
python export_collection.py /path/to/folder collection
```

Where

* `/path/to/folder` is the path where the 2 CSV files will be created, one for collection records and other with embeddings
* `collection` is the name of the collection

To export use the `import_collection.py` script from the virtual env

```bash
python import_collection.py /path/to/folder biology
```

Where

* `/path/to/folder` is the path where the 2 CSV files to be loaded are searched, one for collection records and other with embeddings
* `collection` is the name of the collection

NB: postgres `psql` client is required for these scripts, connection parameters will be read from environment var (`.env` file)

## Langsmith support



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
