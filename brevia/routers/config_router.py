"""API endpoints definitions to handle audio input"""
from typing import Any
from fastapi import APIRouter, HTTPException, status
from brevia.config import read_conf, update_conf, configurable_settings
from brevia.dependencies import get_dependencies

router = APIRouter()


@router.api_route(
    '/config',
    methods=['GET', 'HEAD'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Config'],
)
def get_config():
    """ /config endpoint, read Brevia configuration """
    return read_conf()


@router.api_route(
    '/config/keys',
    methods=['GET', 'HEAD'],
    dependencies=get_dependencies(json_content_type=False),
    tags=['Config'],
)
def get_config_keys():
    """ /config/keys endpoint, read Brevia configuration settings keys """
    return configurable_settings()


@router.api_route(
    '/config',
    methods=['POST'],
    dependencies=get_dependencies(),
    tags=['Config'],
)
def set_config(config: dict[str, Any]):
    """ /config endpoint, set Brevia configuration """
    for key in config.keys():
        if key not in configurable_settings():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'Setting "{key}" is not configurable',
            )
    return update_conf(config)
