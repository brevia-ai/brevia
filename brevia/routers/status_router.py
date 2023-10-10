"""API endpoints definitions to handle audio input"""
from fastapi import APIRouter, Response, status
from brevia.dependencies import get_dependencies
from brevia import connection

router = APIRouter()


@router.api_route(
    '/status',
    methods=['GET', 'HEAD'],
    dependencies=get_dependencies(json_content_type=False),
)
def api_status(response: Response):
    """ /status endpoint, safety check """
    db_status = connection.test_connection()
    if not db_status:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        'db_status': 'OK' if db_status else 'KO'
    }
