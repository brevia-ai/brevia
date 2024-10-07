# syntax=docker/dockerfile:1
FROM python:3.12-alpine

RUN apk add g++

# Extra python env
ENV PYTHONDONTWRITEBYTECODE=0
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV POETRY_VIRTUALENVS_CREATE=false

RUN pip install poetry

WORKDIR /python-docker

COPY . /python-docker/

RUN poetry install --no-interaction --no-ansi

RUN apk del g++

EXPOSE 8000

CMD poetry run db_upgrade && poetry run uvicorn --host 0.0.0.0 --port 8000 main:app
