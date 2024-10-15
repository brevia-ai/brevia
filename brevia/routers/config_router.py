"""API endpoints to Brevia configuration"""
from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from brevia.settings import (
    Settings,
    read_db_conf,
    update_db_conf,
    configurable_settings,
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
    return read_db_conf(db_connection())


@router.api_route(
    '/config/schema',
    methods=['GET', 'HEAD'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Config'],
)
def get_config_schema():
    """ /config/schema endpoint, read Brevia configuration settings keys """
    schema = Settings.model_json_schema()
    props = schema.get('properties', {})
    schema['properties'] = {key: props[key] for key in configurable_settings()}

    return schema


@router.api_route(
    '/config',
    methods=['POST'],
    dependencies=get_dependencies(),
    tags=['Config'],
)
def save_config(config: dict[str, Any]):
    """POST /config endpoint, save Brevia configuration """
    not_configurable = [
        key for key in config.keys() if key not in configurable_settings()
    ]
    if not_configurable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'There are not configurable settings: {",".join(not_configurable)}',
        )
    try:
        Settings(**config)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Invalid configuration: {exc}',
        )

    return update_db_conf(db_connection(), config)
