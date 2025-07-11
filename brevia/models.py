"""Utilities to create langchain LLM and Chat Model instances."""
from abc import ABC, abstractmethod
from glom import glom
from typing import Any
from langchain.chat_models.base import init_chat_model
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel, BaseLLM
from langchain_community.chat_models.fake import FakeListChatModel
from langchain_community.llms.fake import FakeListLLM
from langchain_community.llms.loading import load_llm_from_config
from langchain_community.embeddings.fake import FakeEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI
from brevia.settings import get_settings
from brevia.utilities.types import load_type


class FakeBreviaLLM(FakeListLLM):
    """Fake LLM for testing purposes."""

    def get_token_ids(self, text: str) -> list[int]:
        """Fake for testing purposes."""
        return [10] * 10


LOREM_IPSUM = """{
    "question": "What is lorem ipsum?",
    "answer": "Lorem ipsum dolor sit amet, consectetur adipisici elit,
              sed eiusmod tempor incidunt ut labore et dolore magna aliqua."
}"""


def get_model_config(
    key: str,
    user_config: dict | None = None,
    db_metadata: dict | None = None,
    default: object = None,
) -> object:
    """
    Retrieve a model configuration value by searching in user config, db metadata,
    and settings, in order. Uses glom for safe nested lookup.
    """
    # Check user config and db metadata
    for source in [user_config, db_metadata]:
        if source is not None:
            value = glom(source, key, default=None)
            if value is not None:
                return value

    # Check settings only if it's a known key
    settings = get_settings()
    if hasattr(settings, key):
        value = getattr(settings, key)
        return value.copy() if hasattr(value, "copy") else value

    return default


def load_llm(config: dict) -> BaseLLM:
    """Load langchain LLM, use Fake LLM in test mode"""
    if test_models_in_use():
        return FakeBreviaLLM(responses=[LOREM_IPSUM] * 10)

    return load_llm_from_config(config=config)


class FakeBreviaChatModel(FakeListChatModel):
    """Fake Chat Model for testing purposes."""

    def get_token_ids(self, text: str) -> list[int]:
        """Fake for testing purposes."""
        return [10] * 10


def load_chatmodel(config: dict) -> BaseChatModel:
    """Load Chat Model from Config Dict."""
    if test_models_in_use():
        return FakeBreviaChatModel(responses=[LOREM_IPSUM] * 10)

    chatmodel_aliases = {
        'openai-chat': ChatOpenAI,
        'fake-list-chat-model': FakeListChatModel,
    }
    model_type = config.pop('_type', None)
    if model_type is None:
        return init_chat_model(**config)

    if model_type in chatmodel_aliases:
        llm_cls = chatmodel_aliases[model_type]
    else:
        llm_cls = load_type(
            model_type,
            BaseChatModel,
            'langchain_community.chat_models',
        )

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
        client = OpenAI()
        audio_file = open(file, "rb")
        return client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            **kwargs
        )


def load_audiotranscriber() -> BaseAudio:
    """Load Audio transcriber (only openAI supported for now)."""
    if test_models_in_use():
        return FakeAudio()

    return AudioOpenAI()


def load_embeddings(custom_conf: dict | None = None) -> Embeddings:
    """ Load Embeddings engine """
    settings = get_settings()
    if test_models_in_use():
        return FakeEmbeddings(size=1536)

    config = settings.embeddings.copy() if not custom_conf else custom_conf
    embed_aliases = {
        'openai-embeddings': OpenAIEmbeddings,
        'fake-embeddings': FakeEmbeddings,
    }
    model_type = config.pop('_type')
    if model_type in embed_aliases:
        emb_cls = embed_aliases[model_type]
    else:
        emb_cls = load_type(
            model_type,
            Embeddings,
            'langchain_community.embeddings',
        )

    return emb_cls(**config)


def test_models_in_use() -> bool:
    """Check if test models are in use (via `USE_TEST_MODELS` env var)"""
    return get_settings().use_test_models
