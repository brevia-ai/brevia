"""API endpoints definitions to handle audio input"""
from fastapi import APIRouter, Response, status, Depends
from brevia.dependencies import status_token_auth
from brevia.connection import test_connection
from brevia.settings import get_settings

router = APIRouter()


def status_dependencies() -> list[Depends]:
    """Get /status endpoint dependencies"""
    return [] if not get_settings().tokens_secret else [Depends(status_token_auth)]


@router.api_route(
    '/status',
    methods=['GET', 'HEAD'],
    dependencies=status_dependencies(),
)
def api_status(response: Response):
    """ /status endpoint, safety check """
    db_status = test_connection()
    if not db_status:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        'db_status': 'OK' if db_status else 'KO'
    }
