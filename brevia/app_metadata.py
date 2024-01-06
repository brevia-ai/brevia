"""Create OpenAPI app metadata"""
import logging
import tomli
from brevia.settings import get_settings


OPENAPI_METADATA = [  # Metadata used in OpenAPI representations
    {
        'name': 'Collections',
        'description': 'Operations with Collections.',
    },
    {
        'name': 'Index',
        'description': 'Manage documents index',
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
        'openapi_tags': OPENAPI_METADATA,
    }
