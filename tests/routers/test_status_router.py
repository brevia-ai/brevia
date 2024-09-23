"""Status router tests"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.connection import get_engine
from brevia.routers import status_router
from brevia.settings import get_settings
from brevia.tokens import create_token

app = FastAPI()
app.include_router(status_router.router)
client = TestClient(app)


def test_status_ok():
    """Test /status success"""
    response = client.get('/status', headers={})
    assert response.status_code == 200
    assert response.json() == {
        'db_status': 'OK'
    }


def test_status_fail():
    """Test /status failure"""
    settings = get_settings()
    database = settings.pgvector_database
    settings.pgvector_database = 'non_exixsting_db'
    get_engine.cache_clear()

    response = client.get('/status', headers={})

    settings.pgvector_database = database
    get_engine.cache_clear()

    assert response.status_code == 503


def test_status_token():
    """Test /status access with special token"""
    settings = get_settings()
    settings.tokens_secret = 'secretsecretsecret'
    settings.status_token = 'specialtoken'

    headers = {}
    response = client.get('/status', headers=headers)
    assert response.status_code == 401

    response = client.get('/status?token=specialtoken', headers=headers)
    assert response.status_code == 200

    headers = {'Authorization': 'Something specialtoken'}
    response = client.get('/status', headers=headers)
    assert response.status_code == 401

    token = create_token(user='gustavo', duration=10)
    headers = {'Authorization': f'Bearer {token}'}
    response = client.get('/status', headers=headers)
    assert response.status_code == 200

    settings.tokens_secret = ''
    settings.status_token = ''
