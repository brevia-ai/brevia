"""Settings module"""
import logging
from functools import lru_cache
from typing import Any
from os import environ
from urllib import parse
from fnmatch import fnmatch
from sqlalchemy import NullPool, create_engine, Column, String, func, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Session
from langchain_community.vectorstores.pgembedding import BaseModel
from pydantic import Json
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Brevia settings"""
    model_config = SettingsConfigDict(
        env_file='.env', extra='ignore'
    )

    verbose_mode: bool = False

    # Postgres+pgvector vector db
    pgvector_host: str = 'localhost'
    pgvector_driver: str = 'psycopg2'
    pgvector_port: int = 5432
    pgvector_database: str = 'brevia'
    pgvector_user: str = ''
    pgvector_password: str = ''
    pgvector_pool_size: int = 10
    # optional DSN URI, if set other pgvector_* settings are ignored
    pgvector_dsn_uri: str = ''

    # Tokens
    tokens_secret: str = ''
    tokens_users: str = ''
    status_token: str = ''

    # API keys, tokens...
    # You should use `brevia_env_secrets` to store secrets that
    # must be available as environment variables
    openai_api_key: str = ''
    cohere_api_key: str = ''

    # Test models - only in unit tests
    use_test_models: bool = False

    # Index - text splitter settings
    text_chunk_size: int = 2000
    text_chunk_overlap: int = 200
    text_splitter: Json[dict[str, Any]] = '{}'  # custom splitter settings

    # Search
    search_docs_num: int = 4

    # LLM settings
    qa_completion_llm: Json[dict[str, Any]] = """{
        "_type": "openai-chat",
        "model_name": "gpt-4o-mini",
        "temperature": 0,
        "max_tokens": 1000,
        "verbose": true
    }"""
    qa_followup_llm: Json[dict[str, Any]] = """{
        "_type": "openai-chat",
        "model_name": "gpt-4o-mini",
        "temperature": 0,
        "max_tokens": 200,
        "verbose": true
    }"""
    summarize_llm: Json[dict[str, Any]] = """{
        "_type": "openai-chat",
        "model_name": "gpt-4o",
        "temperature": 0,
        "max_tokens": 2000
    }"""

    # Environment secrets, dictionary of variables that must be present as environment
    # variables
    # (Pydantic throws an error using SecretStr as dict value type)
    brevia_env_secrets: Json[dict[str, str]] = '{}'

    # Embeddings
    embeddings: Json = '{"_type": "openai-embeddings"}'
    # every vendor has its own embeddings vector size, some vendors have multiple sizes
    # this value should be unique in your project to avoid calculation errors
    embeddings_size: int = 1536

    # QA
    qa_no_chat_history: bool = False  # don't load chat history
    qa_followup_sim_threshold: float = 0.735  # similitude threshold in followup
    qa_retriever: Json[dict[str, Any]] = '{}'  # custom retriever settings

    # Summarization
    summ_default_chain: str = 'stuff'
    summ_token_splitter: int = 4000
    summ_token_overlap: int = 500

    # App metadata
    block_openapi_urls: bool = False

    def update(
        self,
        other: dict[str, Any] | BaseSettings,
    ) -> None:
        """Update settings fields, used when updating from db and in unit tests"""
        keys = Settings.model_fields.keys()
        if not isinstance(other, BaseSettings):
            other = {k.lower(): v for k, v in other.items() if hasattr(self, k)}
            keys = other.keys()
            other = Settings(**other)
        for key in keys:
            setattr(self, key, getattr(other, key))

    def setup_environment(self):
        """Setup some useful environment variables"""
        log = logging.getLogger(__name__)
        for key in self.brevia_env_secrets.keys():
            environ[key] = self.brevia_env_secrets.get(key)
            log.info('"%s" env var set', key)
        if self.openai_api_key:
            environ['OPENAI_API_KEY'] = self.openai_api_key
            log.info('"OPENAI_API_KEY" env var set')
        if self.cohere_api_key:
            environ['COHERE_API_KEY'] = self.cohere_api_key
            log.info('"COHERE_API_KEY" env var set')

    def connection_string(self) -> str:
        """ Db connection string from Settings """
        if self.pgvector_dsn_uri:
            return self.pgvector_dsn_uri

        driver = self.pgvector_driver
        host = self.pgvector_host
        port = self.pgvector_port
        database = self.pgvector_database
        user = self.pgvector_user
        password = parse.quote_plus(self.pgvector_password)

        return f"postgresql+{driver}://{user}:{password}@{host}:{port}/{database}"

    def update_from_db(self):
        """Update settings from db"""
        try:
            engine = create_engine(self.connection_string(), poolclass=NullPool)
            insp = inspect(engine)
            if insp.has_table(ConfigStore.__tablename__):
                db_conf = read_db_conf(engine.connect())
                self.update(db_conf)
            engine.dispose()
        except Exception as exc:
            logging.getLogger(__name__).error('Failed to read config from db: %s', exc)


def configurable_settings() -> list[str]:
    keys = Settings.model_fields.keys()
    excluded_keys = [
        'pgvector_*',
        'tokens_*',
        'status_token',
        'use_test_models'
    ]

    return [key for key in keys
            if not any(fnmatch(key, pattern) for pattern in excluded_keys)]


class ConfigStore(BaseModel):
    # pylint: disable=too-few-public-methods,not-callable
    """ Config table """
    __tablename__ = "config"

    config_key = Column(String(), nullable=False, unique=True)
    config_val = Column(String(), nullable=False)
    created = Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    modified = Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


def read_db_conf(connection: Connection) -> dict[str, str]:
    """ Read all config records """
    with Session(connection) as session:
        query = session.query(ConfigStore.config_key, ConfigStore.config_val)
        items = {key: value for key, value in query.all()}
        # Filter out non-configurable settings
        return {key: value
                for key, value in items.items() if key in configurable_settings()}


def update_db_conf(connection: Connection, items: dict[str, str]) -> dict[str, str]:
    """ Update config records """
    # Filter out non-configurable settings
    items = {k: v for k, v in items.items() if k in configurable_settings()}
    with Session(connection) as session:
        session.expire_on_commit = False
        query = session.query(ConfigStore)
        current_conf = {u.config_key: u for u in query.all()}
        for key, value in items.items():
            if key not in current_conf:
                session.add(ConfigStore(config_key=key, config_val=value))
            elif current_conf[key].config_val != value:
                current_conf[key].config_val = value
                session.add(current_conf[key])
        for key in current_conf.keys():
            if key not in items:
                session.delete(current_conf[key])

        session.commit()
    # Clear settings cache, force settings reload
    get_settings.cache_clear()

    return read_db_conf(connection)


@lru_cache
def get_settings():
    """Return Settings object instance just once (using lru_cache)"""
    settings = Settings()
    settings.update_from_db()
    settings.setup_environment()

    return settings
