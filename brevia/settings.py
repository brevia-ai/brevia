"""Settings module"""
import logging
from functools import lru_cache
from typing import Any
from os import environ
from pydantic import Json
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Brevia settings"""
    model_config = SettingsConfigDict(
        env_file='.env', extra='ignore'
    )

    verbose_mode: bool = False
    pgvector_host: str = 'localhost'
    pgvector_driver: str = 'psycopg2'
    pgvector_port: int = 5432
    pgvector_database: str = 'brevia'
    pgvector_user: str = ''
    pgvector_password: str = ''
    pgvector_pool_size: int = 10

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

    # Index - textsplitter settings
    text_chunk_size: int = 2000
    text_chunk_overlap: int = 200

    # Search
    search_docs_num: int = 4

    # LLM settings
    qa_completion_llm: Json[dict[str, Any]] = """{
        "_type": "openai-chat",
        "model_name": "gpt-3.5-turbo-16k",
        "temperature": 0,
        "max_tokens": 1000,
        "verbose": true
    }"""
    qa_followup_llm: Json[dict[str, Any]] = """{
        "_type": "openai-chat",
        "model_name": "gpt-3.5-turbo-16k",
        "temperature": 0,
        "max_tokens": 200,
        "verbose": true
    }"""
    summarize_llm: Json[dict[str, Any]] = """{
        "_type": "openai-chat",
        "model_name": "gpt-3.5-turbo-16k",
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
    feature_qa_lang_detect: bool = False

    # Summarization
    summ_default_chain: str = 'stuff'
    summ_token_splitter: int = 4000
    summ_token_overlap: int = 500

    # App metadata
    block_openapi_urls: bool = False

    def update(
        self,
        other: dict[str, Any],
    ) -> None:
        """Update settings fields, used in unit tests"""
        for field_name in other.keys():
            key = field_name.lower()
            if hasattr(self, key):
                setattr(self, key, other.get(field_name))

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


@lru_cache
def get_settings():
    """Return Settings object instance just once (using lru_cache)"""
    settings = Settings()
    settings.setup_environment()

    return settings
