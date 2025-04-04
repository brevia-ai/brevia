# Brevia Setup

## Requirements

A version of Python 3.10 or higher and [Poetry](https://python-poetry.org/docs/#installation) is required.
A PostgreSQL database version 11 or higher with [`pg_vector`](https://github.com/pgvector/pgvector), but you can use the provided docker image for a quicker setup.

## Quick try

The easiest and fastest way to try Brevia is through Docker. By launching docker compose with the following command you will have a working Brevia system without any setup or configuration:

```bash
docker compose --profile fullstack up
```

At this point you will have:

* Brevia API on http://localhost:8000
* Brevia App UI on http://localhost:3000

To use ports other than 8000 or 3000 just uncomment the variables `BREVIA_API_PORT` or `BREVIA_APP_PORT` in the .env file.

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

To perform a manual setup instead you can follow these steps using poetry, pip or your preferred tool.

#### Using poetry

* create a new project with `poetry new {your-brevia-project}`
* install brevia and its dependencies by running `poetry add brevia`, a virtualenv will automatically be created
* create a new `main.py` starting with a [copy](https://raw.githubusercontent.com/brevia-ai/brevia-cookiecutter/main/%7B%7Bcookiecutter.project_slug%7D%7D/main.py)
* activate the virtualenv by running the `poetry env activate` command
* copy the file `.env.sample` to `.env` and value the environment variables, especially `OPENAI_API_KEY` with the secret key of OpenAI and `PGVECTOR_*` - see the [Configuration](config.md) and [Database](database.md) sections or more details

#### Using pip

* install brevia and its dependencies by running `pip install brevia`
* create a virtualenv with your preferred tool
* create a new `main.py` starting with a [copy](https://raw.githubusercontent.com/brevia-ai/brevia-cookiecutter/main/%7B%7Bcookiecutter.project_slug%7D%7D/main.py)
* copy the file `.env.sample` to `.env` and value the environment variables, especially `OPENAI_API_KEY` with the secret key of OpenAI and `PGVECTOR_*` - see the [Configuration](config.md) and [Database](database.md) sections or more details
* activate your virtualenv
