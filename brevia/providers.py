""" Module to list available providers and models """
import json
import logging
from os import environ
from openai import OpenAI, OpenAIError
from cohere import Client as CohereClient
from ollama import Client as OllamaClient
from anthropic import Client as AnthropicClient
from brevia.connection import db_connection
from brevia.settings import get_settings, update_db_conf


def list_providers():
    """ List available providers and models """
    providers = []
    for provider in PROVIDER_MODELS_MAP:
        models = PROVIDER_MODELS_MAP[provider]()
        item = {'model_provider': provider, 'models': models}
        providers.append(item)

    return providers


def update_providers(force: bool = False):
    """ Update providers list from API"""
    settings = get_settings()
    if settings.providers and not force:
        return
    try:
        providers = list_providers()
        update_db_conf(db_connection(), {'providers': json.dumps(providers)})
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.getLogger(__name__).error('Failed to update providers: %s', exc)


def load_openai_models() -> list | None:
    """ Load OpenAI models """
    try:
        client = OpenAI()
        list = client.models.list().model_dump()
    except OpenAIError:
        return None
    models = []
    for item in list['data']:
        name = item['id']
        if name.startswith('gpt-') or name.startswith('o1') or name.startswith('o3'):
            models.append({'name': name})

    return models


def load_deepseek_models() -> list | None:
    """ Load DeepSeek models """
    try:
        client = OpenAI(
            base_url='https://api.deepseek.com/v1',
            api_key=environ.get('DEEPSEEK_API_KEY'),
        )
        list = client.models.list().model_dump()
    except OpenAIError:
        return None
    models = []
    for item in list['data']:
        name = item['id']
        models.append({'name': name})

    return models


def load_anthropic_models() -> list | None:
    """ Load Anthropic models """
    try:
        client = AnthropicClient()
        list = client.models.list().model_dump()
    except Exception:
        return None
    models = []
    for item in list['data']:
        name = item['id']
        models.append({'name': name})

    return models


def load_cohere_models():
    """ Load Cohere models """
    try:
        co = CohereClient()
        list = co.models.list(page_size=100).model_dump()
    except Exception:
        return None
    models = []
    for item in list['models']:
        name = item['name']
        if 'chat' in item['endpoints']:
            models.append({'name': name, 'tokens_limit': int(item['context_length'])})

    return models


def load_ollama_models():
    """ Load Ollama models """
    try:
        ol = OllamaClient()
        list = ol.list()
    except Exception:
        return None
    models = []
    for item in list['models']:
        name = item['name']
        fam = item['details']['family']
        if fam not in ['bert', 'nomic-bert']:
            models.append({'name': name})

    return models


PROVIDER_MODELS_MAP = {
    'openai': load_openai_models,
    'cohere': load_cohere_models,
    'anthropic': load_anthropic_models,
    'ollama': load_ollama_models,
    'deepseek': load_deepseek_models,
}
