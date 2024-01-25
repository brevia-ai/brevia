"""API endpoints definitions to handle audio input"""
from typing import Annotated
from fastapi import APIRouter, Response, status, Header
from brevia.dependencies import token_auth
from brevia.connection import test_connection
from brevia.settings import get_settings

router = APIRouter()


def check_authorization(token: str | None, authorization: str | None):
    """Get /status endpoint authorization"""
    if not get_settings().tokens_secret:
        return
    if get_settings().status_token and token == get_settings().status_token:
        return
    if authorization and authorization.startswith('Bearer '):
        token = authorization.removeprefix('Bearer ')
    else:
        token = ''
    token_auth(token=token)


@router.api_route(
    '/status',
    methods=['GET', 'HEAD'],
    tags=['Status'],
)
def api_status(
    response: Response,
    token: str | None = None,
    authorization: Annotated[str | None, Header()] = None
):
    """ /status endpoint, safety check """
    check_authorization(token=token, authorization=authorization)
    db_status = test_connection()
    if not db_status:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        'db_status': 'OK' if db_status else 'KO'
    }
