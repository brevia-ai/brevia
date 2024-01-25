"""Models module tests"""
import pytest
from langchain.llms.openai import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.embeddings.fake import FakeEmbeddings
from brevia.settings import get_settings
from brevia.models import (
    load_llm,
    load_chatmodel,
    load_audiotranscriber,
    load_embeddings,
    FakeBreviaLLM,
    FakeBreviaChatModel,
    FakeAudio,
    AudioOpenAI,
    LOREM_IPSUM
)


def test_load_llm():
    """ Test load_llm """
    result = load_llm({'_type': 'openai'})
    assert isinstance(result, FakeBreviaLLM)
    assert result.get_token_ids('') == [10] * 10

    settings = get_settings()
    settings.use_test_models = False
    result = load_llm({'_type': 'openai'})
    assert isinstance(result, OpenAI)
    settings.use_test_models = True


def test_load_chatmodel():
    """ Test load_chatmodel """
    result = load_chatmodel({'_type': 'openai-chat'})
    assert isinstance(result, FakeBreviaChatModel)
    assert result.get_token_ids('') == [10] * 10

    settings = get_settings()
    settings.use_test_models = False
    result = load_chatmodel({'_type': 'openai-chat'})
    assert isinstance(result, ChatOpenAI)
    settings.use_test_models = True


def test_load_chatmodel_failure():
    """ Test load_chatmodel fail"""
    settings = get_settings()
    settings.use_test_models = False
    with pytest.raises(ValueError) as excinfo:
        load_chatmodel({'_type': 'non-existent'})
    assert excinfo is not None
    settings.use_test_models = True


def test_load_audiotranscriber():
    """ Test load_audiotranscriber """
    result = load_audiotranscriber()
    assert isinstance(result, FakeAudio)
    assert result.transcribe(file=None) == {'text': LOREM_IPSUM}

    settings = get_settings()
    settings.use_test_models = False
    result = load_audiotranscriber()
    assert isinstance(result, AudioOpenAI)
    with pytest.raises(Exception) as excinfo:
        result.transcribe(file=None)
    assert excinfo is not None

    settings.use_test_models = True


def test_load_embeddings():
    """ Test load_embeddings """
    result = load_embeddings()
    assert isinstance(result, FakeEmbeddings)

    settings = get_settings()
    settings.use_test_models = False
    result = load_embeddings()
    assert isinstance(result, OpenAIEmbeddings)
    settings.use_test_models = True


def test_load_embeddings_fail():
    """ Test load_embeddings failure"""
    settings = get_settings()
    settings.use_test_models = False
    curr_embeddings = settings.embeddings
    settings.embeddings = {'_type': 'unknown-embeddings'}
    with pytest.raises(ValueError) as exc:
        load_embeddings()
    assert str(exc.value) == 'Loading "unknown-embeddings" Embeddings not supported'
    settings.use_test_models = True
    settings.embeddings = curr_embeddings
