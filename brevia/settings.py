"""Settings module"""
import logging
from functools import lru_cache
from typing import Annotated, Any
from os import environ, getcwd
from urllib import parse
from sqlalchemy import NullPool, create_engine, Column, String, func, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Session
from langchain_community.vectorstores.pgembedding import BaseModel
from langchain.globals import set_verbose
from pydantic import Field, Json, PrivateAttr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Brevia settings"""
    model_config = SettingsConfigDict(
        env_file='.env', extra='ignore'
    )
    _defaults: dict[str, Any] = PrivateAttr(default={})

    verbose_mode: bool = False

    # Postgres+pgvector vector db
    pgvector_host: str = Field(default='localhost', exclude=True)
    pgvector_driver: str = Field(default='psycopg2', exclude=True)
    pgvector_port: int = Field(default=5432, exclude=True)
    pgvector_database: str = Field(default='brevia', exclude=True)
    pgvector_user: str = Field(default='', exclude=True)
    pgvector_password: str = Field(default='', exclude=True)
    pgvector_pool_size: int = Field(default=10, exclude=True)
    # optional DSN URI, if set other pgvector_* settings are ignored
    pgvector_dsn_uri: str = Field(default='', exclude=True)

    # Tokens
    tokens_secret: str = Field(default='', exclude=True)
    tokens_users: str = Field(default='', exclude=True)
    status_token: str = Field(default='', exclude=True)

    # External services API keys (deprecated)
    # You should use `brevia_env_secrets` to store secrets that
    # must be available as environment variables
    openai_api_key: Annotated[
        str,
        Field(deprecated='Use `brevia_env_secrets` instead')
    ] = Field(default='', exclude=True)
    cohere_api_key: Annotated[
        str,
        Field(deprecated='Use `brevia_env_secrets` instead')
    ] = Field(default='', exclude=True)

    # Test models - only in unit tests
    use_test_models: bool = Field(default=False, exclude=True)

    # Index - text splitter settings
    text_chunk_size: int = 2000
    text_chunk_overlap: int = 200
    text_splitter: Json[dict[str, Any]] = '{}'  # custom splitter settings

    # Search
    search_docs_num: int = 4

    # LLM settings
    qa_completion_llm: Json[dict[str, Any]] = """{
        "model": "gpt-4o-mini",
        "model_provider": "openai",
        "temperature": 0,
        "max_tokens": 2000
    }"""
    qa_followup_llm: Json[dict[str, Any]] = """{
        "model": "gpt-4o-mini",
        "model_provider": "openai",
        "temperature": 0,
        "max_tokens": 500
    }"""
    summarize_llm: Json[dict[str, Any]] = """{
        "model": "gpt-4o-mini",
        "model_provider": "openai",
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
    embeddings_size: Annotated[
        int,
        Field(deprecated='Define size in `embeddings` conf')
    ] = Field(default=1536, exclude=True)

    # QA
    qa_no_chat_history: bool = False  # don't load chat history
    qa_followup_sim_threshold: float = 0.735  # similitude threshold in followup
    qa_retriever: Json[dict[str, Any]] = '{}'  # custom retriever settings

    # Summarization
    summ_default_chain: str = 'stuff'
    summ_token_splitter: int = 4000
    summ_token_overlap: int = 500

    # Prompt files base path - local or shared file system
    prompts_base_path: str = Field(default=f'{getcwd()}/brevia/prompts', exclude=True)

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
        """Setup some useful environment variables from `brevia_env_secrets`"""
        log = logging.getLogger(__name__)
        for key, value in self.brevia_env_secrets.items():
            environ[key] = value
            log.info('"%s" env var set', key)

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
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.getLogger(__name__).error('Failed to read config from db: %s', exc)

    def setup_defaults(self):
        """Setup defaults"""
        self._defaults = self.model_dump()

    def get_configurable_schema(self) -> dict[str, Any]:
        """Get JSON Schema of configurable properties, with actual defaults"""
        schema = self.model_json_schema(mode='serialization')
        for key, value in schema['properties'].items():
            value['default'] = self._defaults[key]

        return schema


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


@lru_cache
def get_configurable_keys():
    """Get configurable keys"""
    return Settings().model_dump().keys()


def read_db_conf(connection: Connection) -> dict[str, str]:
    """ Read all config records """
    with Session(connection) as session:
        query = session.query(ConfigStore.config_key, ConfigStore.config_val)
        # Filter out non-configurable settings
        keys = get_configurable_keys()
        return {key: value for key, value in query.all() if key in keys}


def update_db_conf(connection: Connection, items: dict[str, str]) -> dict[str, str]:
    """ Update some config items """
    # Filter out non-configurable settings
    keys = get_configurable_keys()
    items = {k: v for k, v in items.items() if k in keys}
    # validate items - this will raise a validation Error a key is not valid
    try:
        Settings(**items)
    except ValidationError as exc:
        logging.getLogger(__name__).error('Invalid settings: %s', exc)
        raise exc

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

        session.commit()
    # Clear settings cache, force settings reload
    get_settings.cache_clear()

    return read_db_conf(connection)


def reset_db_conf(connection: Connection, items: list[str]) -> dict[str, str]:
    """ Reset to defatul some config items """
    # Filter out non-configurable settings
    keys = get_configurable_keys()
    items = [k for k in items if k in keys]
    with Session(connection) as session:
        session.expire_on_commit = False
        query = session.query(ConfigStore)
        current_conf = {u.config_key: u for u in query.all()}
        for key in items:
            if key in current_conf:
                session.delete(current_conf[key])
        session.commit()
    # Clear settings cache, force settings reload
    get_settings.cache_clear()

    return read_db_conf(connection)


@lru_cache
def get_settings():
    """Return Settings object instance just once (using lru_cache)"""
    settings = Settings()
    settings.setup_defaults()
    settings.update_from_db()
    settings.setup_environment()

    set_verbose(settings.verbose_mode)

    return settings
