"""Models module tests"""
import pytest
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.embeddings.fake import FakeEmbeddings
from langchain_community.llms.openai import OpenAI
from langchain_ollama.chat_models import ChatOllama
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
    # load with alias
    result = load_chatmodel({'_type': 'openai-chat'})
    assert isinstance(result, ChatOpenAI)
    # load with class path name
    result = load_chatmodel({'_type': 'langchain_openai.chat_models.ChatOpenAI'})
    assert isinstance(result, ChatOpenAI)

    settings.use_test_models = True


def test_load_init_chat_model():
    """ Test load_chatmodel with `init_chat_model` structure"""
    settings = get_settings()
    settings.use_test_models = False
    # load openai chat model
    result = load_chatmodel(
        {'model': 'gpt-4o', 'model_provider': 'openai', 'max_tokens': 1000}
    )
    assert isinstance(result, ChatOpenAI)
    assert result.max_tokens == 1000
    # load with class path name
    result = load_chatmodel(
        {'model': 'llama3.2', 'model_provider': 'ollama', 'temperature': 0.1}
    )
    assert isinstance(result, ChatOllama)
    assert result.temperature == 0.1

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
    # load default
    result = load_embeddings()
    assert isinstance(result, OpenAIEmbeddings)
    # load with alias
    result = load_embeddings({'_type': 'openai-embeddings'})
    assert isinstance(result, OpenAIEmbeddings)
    # load with class path name
    result = load_embeddings({'_type': 'langchain_openai.embeddings.OpenAIEmbeddings'})
    assert isinstance(result, OpenAIEmbeddings)
    settings.use_test_models = True


def test_load_embeddings_fail():
    """ Test load_embeddings failure"""
    settings = get_settings()
    settings.use_test_models = False
    curr_embeddings = settings.embeddings
    # load with missing alias
    settings.embeddings = {'_type': 'unknown-embeddings'}
    with pytest.raises(ValueError) as exc:
        load_embeddings()
    assert str(exc.value).startswith('Class "unknown-embeddings" not found in ')
    # load with missing class name path
    settings.embeddings = {'_type': 'some.unknown.StrangeEmbeddings'}
    with pytest.raises(ValueError) as exc:
        load_embeddings()
    assert str(exc.value) == 'Module "some.unknown" not found'
    settings.use_test_models = True
    settings.embeddings = curr_embeddings
