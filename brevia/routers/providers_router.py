"""API endpoints definitions to show available providers and models"""
from fastapi import APIRouter, HTTPException, status
from brevia.dependencies import get_dependencies
from brevia.providers import list_providers, single_provider

router = APIRouter()


@router.api_route(
    '/providers',
    methods=['GET'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Providers'],
)
def api_providers(list_models: bool = True):
    """ /providers endpoint, list available providers and models """
    return list_providers(list_models=list_models)


@router.api_route(
    '/providers/{provider}',
    methods=['GET'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Providers'],
)
def provider_models(provider: str):
    """ /providers/{provider} endpoint, list available models for a provider """
    res = single_provider(provider=provider)
    if not res:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Providers '{provider}' not found",
        )

    return res
