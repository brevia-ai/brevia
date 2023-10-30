"""Models module tests"""
from os import environ
import pytest
from langchain.llms.openai import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.embeddings.fake import FakeEmbeddings
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

    current = environ.get('USE_TEST_MODELS')
    del environ['USE_TEST_MODELS']
    result = load_llm({'_type': 'openai'})
    assert isinstance(result, OpenAI)
    environ['USE_TEST_MODELS'] = current


def test_load_chatmodel():
    """ Test load_chatmodel """
    result = load_chatmodel({'_type': 'openai-chat'})
    assert isinstance(result, FakeBreviaChatModel)
    assert result.get_token_ids('') == [10] * 10

    current = environ.get('USE_TEST_MODELS')
    del environ['USE_TEST_MODELS']
    result = load_chatmodel({'_type': 'openai-chat'})
    assert isinstance(result, ChatOpenAI)
    environ['USE_TEST_MODELS'] = current


def test_load_chatmodel_failure():
    """ Test load_chatmodel fail"""
    current = environ.get('USE_TEST_MODELS')
    del environ['USE_TEST_MODELS']
    with pytest.raises(ValueError) as excinfo:
        load_chatmodel({'_type': 'non-existent'})
    assert excinfo is not None
    environ['USE_TEST_MODELS'] = current


def test_load_audiotranscriber():
    """ Test load_audiotranscriber """
    result = load_audiotranscriber()
    assert isinstance(result, FakeAudio)
    assert result.transcribe(file=None) == {'text': LOREM_IPSUM}

    current = environ.get('USE_TEST_MODELS')
    del environ['USE_TEST_MODELS']
    result = load_audiotranscriber()
    assert isinstance(result, AudioOpenAI)
    with pytest.raises(Exception) as excinfo:
        result.transcribe(file=None)
    assert excinfo is not None

    environ['USE_TEST_MODELS'] = current


def test_load_embeddings():
    """ Test load_embeddings """
    result = load_embeddings()
    assert isinstance(result, FakeEmbeddings)

    current = environ.get('USE_TEST_MODELS')
    del environ['USE_TEST_MODELS']
    result = load_embeddings()
    assert isinstance(result, OpenAIEmbeddings)
    environ['USE_TEST_MODELS'] = current
