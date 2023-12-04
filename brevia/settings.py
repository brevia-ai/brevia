"""Settings module"""
from functools import lru_cache
from typing import Iterable, Any
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

    # API keys, tokens...
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
    qa_completion_llm: Json = """{
        "_type": "openai-chat",
        "model_name": "gpt-3.5-turbo-16k",
        "temperature": 0,
        "max_tokens": 1000,
        "verbose": true
    }"""
    qa_followup_llm: Json = """{
        "_type": "openai-chat",
        "model_name": "gpt-3.5-turbo-16k",
        "temperature": 0,
        "max_tokens": 200,
        "verbose": true
    }"""
    summarize_llm: Json = """{
        "_type": "openai-chat",
        "model_name": "gpt-3.5-turbo-16k",
        "temperature": 0,
        "max_tokens": 2000
    }"""

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

    # langsmith
    langchain_tracing_v2: bool = False
    langchain_endpoint: str = ''
    langchain_api_key: str = ''
    langchain_project: str = ''

    def update(
        self,
        other: Iterable[tuple[str, Any]],
    ) -> None:
        """Update settings fields, used in unit tests"""
        for field_name, value in other:
            setattr(self, field_name, value)

    def setup_environment(self):
        """Setup some useful environment variables"""
        if self.openai_api_key:
            environ['OPENAI_API_KEY'] = self.openai_api_key
        if self.cohere_api_key:
            environ['COHERE_API_KEY'] = self.cohere_api_key
        if self.langchain_tracing_v2:
            environ['LANGCHAIN_TRACING_V2'] = "true"
            environ['LANGCHAIN_ENDPOINT'] = self.langchain_endpoint
            environ['LANGCHAIN_API_KEY'] = self.langchain_api_key
            environ['LANGCHAIN_PROJECT'] = self.langchain_project
        return


@lru_cache
def get_settings():
    settings = Settings()
    settings.setup_environment()

    return settings
