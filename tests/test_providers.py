"""Providers module tests"""
from unittest.mock import patch, MagicMock
from openai import OpenAIError
from brevia.settings import get_settings
from brevia.providers import (
    list_providers,
    update_providers,
    load_openai_models,
    load_deepseek_models,
    load_anthropic_models,
    load_cohere_models,
    load_ollama_models,
)


def load_mock_provider_models_map():
    """ Load mock provider models map """
    return [{'name': 'mock_model'}]


@patch('brevia.providers.PROVIDER_MODELS_MAP')
def test_list_providers(mock_provider_models_map):
    """ Test list_providers function """
    mock_provider_models_map.items.return_value = ['mock_provider']
    mock_provider_models_map.get.return_value = load_mock_provider_models_map

    providers = list_providers()
    assert providers == [{
            'model_provider': 'mock_provider',
            'models': [{'name': 'mock_model'}],
        }]


@patch('brevia.providers.get_settings')
@patch('brevia.providers.update_db_conf')
@patch('brevia.providers.db_connection')
@patch('brevia.providers.list_providers')
def test_update_providers(mock_list_providers, mock_db_connection,
                          mock_update_db_conf, mock_get_settings):
    """ Test update_providers function """
    mock_get_settings.return_value = MagicMock(providers=None)
    mock_list_providers.return_value = [{
        'model_provider': 'mock_provider',
        'models': [{'name': 'mock_model'}],
    }]

    update_providers()

    mock_list_providers.assert_called_once()
    fake = '[{"model_provider": "mock_provider", "models": [{"name": "mock_model"}]}]'
    mock_update_db_conf.assert_called_once_with(mock_db_connection(), {
        'providers': fake,
    })


def test_update_providers_skip():
    """ Test update_providers function when providers data already in settings """
    fake_providers = [{
        'model_provider': 'mock_provider',
        'models': [{'name': 'mock_model'}],
    }]
    settings = get_settings()
    current = settings.providers
    settings.providers = fake_providers

    update_providers()

    assert settings.providers == fake_providers

    settings.providers = current



@patch('brevia.providers.OpenAI')
def test_load_openai_models(mock_openai):
    """ Test load_openai_models function """
    mock_client = MagicMock()
    mock_client.models.list.return_value.model_dump.return_value = {
        'data': [{'id': 'gpt-3'}, {'id': 'o1-model'}, {'id': 'other-model'}]}
    mock_openai.return_value = mock_client

    models = load_openai_models()
    assert models == [{'name': 'gpt-3'}, {'name': 'o1-model'}]


@patch('brevia.providers.OpenAI')
def test_load_deepseek_models(mock_openai):
    """ Test load_deepseek_models function """
    mock_client = MagicMock()
    mock_client.models.list.return_value.model_dump.return_value = {
        'data': [{'id': 'deepseek-model'}]
    }
    mock_openai.return_value = mock_client

    models = load_deepseek_models()
    assert models == [{'name': 'deepseek-model'}]


@patch('brevia.providers.AnthropicClient')
def test_load_anthropic_models(mock_anthropic):
    """ Test load_anthropic_models function """
    mock_client = MagicMock()
    mock_client.models.list.return_value.model_dump.return_value = {
        'data': [{'id': 'anthropic-model'}]
    }
    mock_anthropic.return_value = mock_client

    models = load_anthropic_models()
    assert models == [{'name': 'anthropic-model'}]


@patch('brevia.providers.CohereClient')
def test_load_cohere_models(mock_cohere):
    """ Test load_cohere_models function """
    mock_client = MagicMock()
    mock_client.models.list.return_value.model_dump.return_value = {
        'models': [
            {'name': 'cohere-model', 'endpoints': ['chat'], 'context_length': '4096'}
        ]
    }
    mock_cohere.return_value = mock_client

    models = load_cohere_models()
    assert models == [{'name': 'cohere-model', 'tokens_limit': 4096}]


@patch('brevia.providers.OllamaClient')
def test_load_ollama_models(mock_ollama):
    """ Test load_ollama_models function """
    mock_client = MagicMock()
    mock_client.list.return_value = {
        'models': [{'name': 'ollama-model', 'details': {'family': 'not-bert'}}]
    }
    mock_ollama.return_value = mock_client

    models = load_ollama_models()
    assert models == [{'name': 'ollama-model'}]


@patch('brevia.providers.OpenAI')
@patch('brevia.providers.OllamaClient')
@patch('brevia.providers.AnthropicClient')
@patch('brevia.providers.CohereClient')
def test_load_models_exceptions(mock_openai, mock_ollama, mock_anthropic, mock_cohere):
    """ Test load models exceptions """

    mock_client = MagicMock()
    mock_client.models.list.side_effect = OpenAIError('API error')
    mock_client.list.side_effect = Exception('API error')
    mock_openai.return_value = mock_client
    mock_ollama.return_value = mock_client
    mock_anthropic.return_value = mock_client
    mock_cohere.return_value = mock_client

    assert load_openai_models() is None
    assert load_deepseek_models() is None
    assert load_anthropic_models() is None
    assert load_cohere_models() is None
    assert load_ollama_models() is None
