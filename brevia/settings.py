"""Settings module"""
from functools import lru_cache
from typing import Iterable, Any
from pydantic import BaseModel, Json
from pydantic_settings import BaseSettings, SettingsConfigDict


class PgVectorSettings(BaseModel):
    """Postgres with pg_vector connection settings"""
    host: str = 'localhost'
    driver: str = 'psycopg2'
    port: int = 5432
    database: str = 'brevia'
    user: str = ''
    password: str = ''
    pool_size: int = 10


class Settings(BaseSettings):
    """Brevia settings"""
    model_config = SettingsConfigDict(
        env_file='.env', extra='ignore', env_nested_delimiter='_'
    )

    verbose_mode: bool = False
    pgvector: PgVectorSettings

    tokens_secret: str = ''
    tokens_users: str = ''

    # API keys
    openai_api_key: str = ''

    # Test models - only in unit tests
    use_test_models: bool = False

    # Index - textsplitter settings
    text_chunk_size: int = 2000
    text_chunk_overlap: int = 200

    search_docs_num: int = 4

    # LLM settings
    embeddings: Json = '{}'
    qa_llm: Json = '{}'
    qa_fup_llm: Json = '{}'
    summ_llm: Json = '{}'

    def update(
        self,
        other: Iterable[tuple[str, Any]],
    ) -> None:
        """Update settings fields, used in unit tests"""
        for field_name, value in other:
            setattr(self, field_name, value)


@lru_cache
def get_settings():
    return Settings()
