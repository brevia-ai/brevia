"""Collections handling functions (DEPRECATED)"""
import warnings
from brevia.collections_tools import (
    collections_info,
    collection_name_exists,
    collection_exists,
    create_collection,
    update_collection,
    delete_collection,
    single_collection,
    single_collection_by_name,
)

warnings.warn(
    "'collections' module is deprecated; use 'collections_tools' instead.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    'collections_info',
    'collection_name_exists',
    'collection_exists',
    'create_collection',
    'update_collection',
    'delete_collection',
    'single_collection',
    'single_collection_by_name',
]
