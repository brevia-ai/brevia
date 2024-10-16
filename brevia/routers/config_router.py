"""API endpoints to Brevia configuration"""
from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from brevia.settings import (
    Settings,
    get_configurable_keys,
    get_settings,
    reset_db_conf,
    update_db_conf,
)
from brevia.dependencies import get_dependencies
from brevia.connection import db_connection

router = APIRouter()


@router.api_route(
    '/config',
    methods=['GET', 'HEAD'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Config'],
)
def get_config():
    """ /config endpoint, read Brevia configuration """
    return get_settings().model_dump()


@router.api_route(
    '/config/schema',
    methods=['GET', 'HEAD'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Config'],
)
def get_config_schema():
    """ /config/schema endpoint, read Brevia configuration settings keys """
    return get_settings().get_configurable_schema()


def check_keys(keys: list[str]):
    """Check if all keys are configurable"""
    not_configurable = [
        key for key in keys if key not in get_configurable_keys()
    ]
    if not_configurable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'There are not configurable settings: {",".join(not_configurable)}',
        )


@router.api_route(
    '/config',
    methods=['POST'],
    dependencies=get_dependencies(),
    tags=['Config'],
)
def save_config(config: dict[str, Any]):
    """POST /config endpoint, save Brevia configuration """
    check_keys(config.keys())

    try:
        Settings(**config)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Invalid configuration: {exc}',
        )

    return update_db_conf(db_connection(), config)


@router.api_route(
    '/config/reset',
    methods=['POST'],
    dependencies=get_dependencies(),
    tags=['Config'],
)
def reset_config(keys: list[str]):
    """POST /config/reset endpoint, reset to default a list of settings """
    check_keys(keys)

    return reset_db_conf(db_connection(), keys)
