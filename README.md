#

<img src="https://chatlas-media.s3.eu-central-1.amazonaws.com/brand/brevia-brand.png" width="400">

[![Github Actions CS](https://github.com/brevia-ai/brevia/workflows/cs/badge.svg)](https://github.com/brevia-ai/brevia/actions?query=workflow%3Acs)
[![Github Actions Unit](https://github.com/brevia-ai/brevia/workflows/unit/badge.svg)](https://github.com/brevia-ai/brevia/actions?query=workflow%3Aunit)
![Python Versions](https://img.shields.io/pypi/pyversions/brevia.svg)
[![Version](https://img.shields.io/pypi/v/brevia.svg?label=brevia)](https://pypi.org/project/brevia/)
[![License](https://img.shields.io/badge/License-MIT-orange.svg)](https://github.com/brevia-ai/brevia/blob/main/LICENSE)

The repository contains a minimal LLM API project in Python based on LangChain for interaction with LLM and FastAPI for the API interface.

## Requirements

A version of Python 3.10 or higher and [Poetry](https://python-poetry.org/docs/#installation) is required.

It is recommended to use virtualenv in the project.
Check the settings with

```bash
poetry config --list
```

Check that the `virtualenvs.in-project` configuration is `true` otherwise launch:

```bash
poetry config virtualenvs.in-project true
```

## Setup

* install the dependencies by running `poetry install`, a virtualenv will automatically be created in the `.venv` folder.
* then activate the virtualenv by running the `poetry shell` command.
* copy the file `.env.sample` to `.env` and value the environment variables, especially `OPENAI_API_KEY` with the secret key of OpenAI and `PGVECTOR_*` see the [Database](#database) section

## Update packages

You use `poetry update` which will update the `poetry.lock` lock file.
To change versions of dependencies you can also directly edit `pyproject.toml` in the `[tool.poetry.dependencies]` section.

## Database

Run `docker compose --profile admin up` to run postgres+pgvector and pgadmin docker images.

With your browser, open `pgadmin` at http://localhost:4000

The `4000` port is configurable with the `PGADMIN_PORT` environment var in the `.env` file.

* login to pgadmin with `PGADMIN_DEFAULT_*` credentials from the .env file.
* create a connection with `Add New Server` by setting.
  * in General `brevia` or other name of your choice (`PGVECTOR_DATABASE`).
  * in Connection as host name `pgdatabase` and choose a Username to Password (`PGVECTOR_USER`, `PGVECTOR_PASSWORD`)

Launch migrations to create the initial schema with [Alembic](https://alembic.sqlalchemy.org)

```bash
alembic upgrade head
```

## Test setup

To verify that the setup is correct, run

```py
python brevia/scripts/csv_import.py data/test_min_dataset.csv test
```

To create indexing from a test CSV with one line.
If at the end in output you find.
`Index collection {name} updated with {n} documents and {n} texts`
then everything is ok.

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

## server API

To start the server, type the following command from virtualenv:

```bash
uvicorn main:app --reload
```

The server will start executing on port `8000`.

## Docker

To launch the docker image of the API along with the Postgres service use

```bash
docker compose --profile api up
```

To launch the PgAdmin docker image along with Postgres use

```bash
docker compose --profile admin up
```

To launch the docker image of the APP and API along with Postgres

```bash
docker compose --profile app up
```

The version of the docker image used is defined in the `.env` file in the environment variables `API_VERSION` for the API and `APP_VERSION` for the app

## Tracing log

To enable the call tracing feature, built in langchain add/uncomment the system variable on `app.py`:

```py
environ["LANGCHAIN_HANDLER"] = langchain
```

ensuring that it is executed before any operation on the langchain libraries.

Start the server via docker images from the console:

```bash
langchain-server
```

Navigate to `http://localhost:4173/` to display the trace control panel and use the default session.

To change the session name set:

```py
.environ ["LANGCHAIN_SESSION"] = "my_session" # Making sure that this session actually exists. You can create a new session in the UI.
```

While to dynamically change session in the code DO NOT set the environment variable LANGCHAIN_SESSION, use instead:

```py
langchain.set_tracing_callback_manager(session_name = "my_session")
```

## Access Tokens

There is a built-in basic support for access tokens for API security

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
