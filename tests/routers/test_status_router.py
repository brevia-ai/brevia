"""Status router tests"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import status_router
from brevia.settings import get_settings

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

    response = client.get('/status', headers={})

    settings.pgvector_database = database

    assert response.status_code == 503
