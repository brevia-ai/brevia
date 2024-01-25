"""Generati OpenAPI metadata"""
import logging
import tomli
from typing import Any
from fastapi import FastAPI, APIRouter
from brevia.routers.app_routers import add_routers
from brevia.settings import get_settings


OPENAPI_TAGS = [  # Tags used in OpenAPI representations
    {
        'name': 'Collections',
        'description': 'Operations with Collections.',
    },
    {
        'name': 'Index',
        'description': 'Manage documents index',
    },
    {
        'name': 'Chat',
        'description': 'Chat on documents collections, retrieve chat history',
    },
    {
        'name': 'Analysis',
        'description': 'Document analisys, summarization, audio transcription',
    },
    {
        'name': 'Status',
        'description': 'API status',
    },
]


def metadata(py_proj_path: str) -> dict[str, str]:
    """Read app metadata from pyproject"""
    if get_settings().block_openapi_urls:
        return {
            'docs_url': None,
            'redoc_url': None,
        }

    try:
        with open(py_proj_path, 'rb') as f:
            py_meta = tomli.load(f)
            meta = py_meta['tool']['poetry']
    except Exception as exc:
        msg = f'{type(exc).__name__}: {exc}'
        logging.getLogger(__name__).error('Error reading app metadata: %s', msg)
        meta = {}

    return {
        'title': meta.get('name', 'Brevia'),
        'description': meta.get('description', '[unable to read app metadata]'),
        'version': meta.get('version', 'unknown'),
        'openapi_tags': OPENAPI_TAGS,
    }


def brevia_openapi(
    py_proj_path: str,
    new_routes: list[APIRouter] = []
) -> dict[str, Any]:
    """Generate Brevia OpenAPI metadata"""
    meta = metadata(py_proj_path)
    app = FastAPI(**meta)
    add_routers(app)
    for router in new_routes:
        app.include_router(router)
    openapi_schema = app.openapi()
    # Comment to show how to extend openapi metadata
    # openapi_schema["info"]["x-logo"] = {
    #     "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    # }
    return openapi_schema
