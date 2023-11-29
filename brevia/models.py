"""Utilities to create langchain LLM and Chat Model instances."""
from abc import ABC, abstractmethod
from typing import Any
from langchain.llms.loading import load_llm_from_config
from langchain.llms.base import BaseLLM
from langchain.llms.fake import FakeListLLM
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import (
    ChatOpenAI,
    ChatAnthropic,
    ChatCohere,
    FakeListChatModel
)
from langchain.embeddings import OpenAIEmbeddings, CohereEmbeddings, FakeEmbeddings
from langchain.embeddings.base import Embeddings
from openai import Audio
from brevia.settings import get_settings


class FakeBreviaLLM(FakeListLLM):
    """Fake LLM for testing purposes."""
    def get_token_ids(self, text: str) -> list[int]:
        return [10] * 10


LOREM_IPSUM = """Lorem ipsum dolor sit amet, consectetur adipisici elit,
sed eiusmod tempor incidunt ut labore et dolore magna aliqua."""


def load_llm(config: dict) -> BaseLLM:
    """Load langchain LLM, use Fake LLM in test mode"""
    if test_models_in_use():
        return FakeBreviaLLM(responses=[LOREM_IPSUM] * 10)

    return load_llm_from_config(config=config)


CHAT_MODEL_TYPES: dict[str, BaseChatModel] = {
    'openai-chat': ChatOpenAI,
    'cohere-chat': ChatCohere,
    'anthropic-chat': ChatAnthropic,
    'fake-list-chat-model': FakeListChatModel,
}


class FakeBreviaChatModel(FakeListChatModel):
    """Fake LLM for testing purposes."""
    def get_token_ids(self, text: str) -> list[int]:
        return [10] * 10


def load_chatmodel(config: dict) -> BaseChatModel:
    """Load Chat Model from Config Dict."""
    if test_models_in_use():
        return FakeBreviaChatModel(responses=[LOREM_IPSUM] * 10)

    config_type = config.pop('_type')
    if config_type not in CHAT_MODEL_TYPES:
        raise ValueError(f"Loading {config_type} Chat Model not supported")

    llm_cls = CHAT_MODEL_TYPES[config_type]
    return llm_cls(**config)


class BaseAudio(ABC):
    """Base class for Audio transcription"""
    @abstractmethod
    def transcribe(self, file: Any, **kwargs) -> dict:
        """transcribe Audio"""


class FakeAudio(BaseAudio):
    """Test class for Audio transcription"""
    def transcribe(self, file: Any, **kwargs) -> dict:
        """transcribe Audio"""
        return {'text': LOREM_IPSUM}


class AudioOpenAI(BaseAudio):
    """OpenAI Audio transcription"""
    def transcribe(self, file: Any, **kwargs) -> dict:
        """transcribe Audio"""
        return Audio.transcribe(
            file=file,
            **kwargs,
        )


def load_audiotranscriber() -> BaseAudio:
    """Load Audio transcriber (only openAI supported for now)."""
    if test_models_in_use():
        return FakeAudio()

    return AudioOpenAI()


EMBEDDING_TYPES: dict[str, BaseChatModel] = {
    'openai-embeddings': OpenAIEmbeddings,
    'cohere-embeddings': CohereEmbeddings,
    'fake-embeddings': FakeEmbeddings,
}


def load_embeddings() -> Embeddings:
    """ Load Embeddings engine """
    settings = get_settings()
    if test_models_in_use():
        return FakeEmbeddings(size=settings.embeddings_size)

    config = settings.embeddings.copy()
    config_type = config.pop('_type', None)
    if config_type not in EMBEDDING_TYPES:
        raise ValueError(f'Loading "{config_type}" Embeddings not supported')

    emb_cls = EMBEDDING_TYPES[config_type]
    return emb_cls(**config)


def test_models_in_use() -> bool:
    """Check if test models are in use (via `USE_TEST_MODELS` env var)"""
    return get_settings().use_test_models
