"""Status router tests with special token"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.settings import get_settings


def test_status_token():
    """Test /status access with special token"""
    settings = get_settings()
    settings.tokens_secret = 'secretsecretsecret'
    settings.status_token = 'specialtoken'

    from brevia.routers import status_router
    app2 = FastAPI()
    app2.include_router(status_router.router)
    client2 = TestClient(app2)

    headers = {}
    response = client2.get('/status', headers=headers)
    assert response.status_code == 401

    headers = {'Authorization': 'Bearer specialtoken'}
    response = client2.get('/status', headers=headers)
    assert response.status_code == 200

    settings.tokens_secret = ''
    settings.status_token = ''
