"""API endpoints definitions to show available providers and models"""
from fastapi import APIRouter
from brevia.dependencies import get_dependencies
from brevia.providers import list_providers

router = APIRouter()


@router.api_route(
    '/providers',
    methods=['GET'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Providers'],
)
def api_providers():
    """ /providers endpoint, list available providers and models """
    return list_providers()
