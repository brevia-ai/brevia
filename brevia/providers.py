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


def list_providers(list_models: bool = True) -> list:
    """ List available providers and models """
    providers = []
    for provider in PROVIDER_MODELS_MAP.keys():
        item = {'model_provider': provider}
        if list_models:
            models = PROVIDER_MODELS_MAP.get(provider)()
            item['models'] = models
        providers.append(item)

    return providers


def single_provider(provider: str) -> dict | None:
    """ List available models for a provider """
    if provider not in PROVIDER_MODELS_MAP:
        return None

    models = PROVIDER_MODELS_MAP.get(provider)()
    return {'model_provider': provider, 'models': models}


def update_providers(force: bool = False):
    """ Update providers list in settings from API and save providers to DB """
    log = logging.getLogger(__name__)
    settings = get_settings()
    if settings.providers and not force:
        return
    try:
        providers = list_providers()
        log.info('Adding "providers" to brevia configuration DB')
        update_db_conf(db_connection(), {'providers': json.dumps(providers)})
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.error('Failed to update providers: %s', exc)


def load_openai_models() -> list | None:
    """ Load OpenAI models """
    try:
        client = OpenAI()
        list_models = client.models.list().model_dump()
    except OpenAIError:
        return None
    models = []
    for item in list_models['data']:
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
        list_models = client.models.list().model_dump()
    except OpenAIError:
        return None
    models = []
    for item in list_models['data']:
        name = item['id']
        models.append({'name': name})

    return models


def load_anthropic_models() -> list | None:
    """ Load Anthropic models """
    try:
        client = AnthropicClient()
        list_models = client.models.list().model_dump()
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    models = []
    for item in list_models['data']:
        name = item['id']
        models.append({'name': name})

    return models


def load_cohere_models():
    """ Load Cohere models """
    try:
        co = CohereClient()
        list_models = co.models.list(page_size=100).model_dump()
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    models = []
    for item in list_models['models']:
        name = item['name']
        if 'chat' in item['endpoints']:
            models.append({'name': name, 'tokens_limit': int(item['context_length'])})

    return models


def load_ollama_models():
    """ Load Ollama models """
    try:
        ol = OllamaClient()
        list_models = ol.list()
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    models = []
    for item in list_models['models']:
        name = item['model']
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
