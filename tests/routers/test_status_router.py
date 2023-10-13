from os import environ
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import status_router

app = FastAPI()
app.include_router(status_router.router)
client = TestClient(app)


def test_status_ok():
    response = client.get('/status', headers={})
    assert response.status_code == 200
    assert response.json() == {
        'db_status': 'OK'
    }


def test_status_fail():
    database = environ.get("PGVECTOR_DATABASE")
    environ['PGVECTOR_DATABASE'] = 'non_exixsting_db'

    response = client.get('/status', headers={})

    environ["PGVECTOR_DATABASE"] = database

    assert response.status_code == 503
