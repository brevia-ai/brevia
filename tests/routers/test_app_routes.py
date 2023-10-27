"""Status router tests"""
from fastapi import FastAPI
from brevia.routers.app_routers import add_routers


def test_app_router():
    """Test /status success"""
    app = FastAPI()
    add_routers(app)
    url_list = set([route.path for route in app.routes])
    expected = [
        '/index',
        '/index/upload',
        '/index/{collection_id}/{document_id}',
        '/summarize',
        '/upload_summarize',
        '/upload_analyze',
        '/collections',
        '/collections/{uuid}',
        '/transcribe',
        '/jobs/{uuid}',
        '/chat_history',
        '/prompt',
        '/search',
        '/status'
    ]

    assert all(x in url_list for x in expected)
