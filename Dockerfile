# syntax=docker/dockerfile:1
FROM python:3.12-alpine AS builder

RUN apk add g++

RUN pip install poetry

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /python-docker

COPY pyproject.toml poetry.lock /python-docker/
RUN touch README.md

RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --no-root

COPY . /python-docker/

RUN poetry install

RUN apk del g++

# Runtime image
FROM python:3.12-alpine AS runtime

WORKDIR /python-docker

ENV PORT=8000 \
    VIRTUAL_ENV=/python-docker/.venv \
    PATH="/python-docker/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY . /python-docker/

EXPOSE ${PORT}

CMD ["sh", "-c", "db_upgrade && uvicorn main:app --host '' --port $PORT"]
