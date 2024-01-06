# Brevia Setup

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

To perform a manual setup instead you can follow these steps using poetry, pip or your preferred tool.

### Using poetry

* create a new project with `poetry new {your-brevia-project}`
* install brevia and its dependencies by running `poetry add brevia`, a virtualenv will automatically be created
* create a new `main.py` starting with a [copy](https://raw.githubusercontent.com/brevia-ai/brevia-cookiecutter/main/%7B%7Bcookiecutter.project_slug%7D%7D/main.py)
* activate the virtualenv by running the `poetry shell` command
* copy the file `.env.sample` to `.env` and value the environment variables, especially `OPENAI_API_KEY` with the secret key of OpenAI and `PGVECTOR_*` see the [Database](#database) section

### Using pip

* install brevia and its dependencies by running `pip install brevia`
* create a virtualenv with your preferred tool
* create a new `main.py` starting with a [copy](https://raw.githubusercontent.com/brevia-ai/brevia-cookiecutter/main/%7B%7Bcookiecutter.project_slug%7D%7D/main.py)
* copy the file `.env.sample` to `.env` and value the environment variables, especially `OPENAI_API_KEY` with the secret key of OpenAI and `PGVECTOR_*` see the [Database](#database) section
* activate your virtualenv
