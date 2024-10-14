"""Status router tests"""
from json import dumps
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import config_router
from brevia.settings import configurable_settings
from tests import conftest

app = FastAPI()
app.include_router(config_router.router)
client = TestClient(app)


def test_get_config():
    """Test /config endpoint"""
    response = client.get('/config', headers={})
    assert response.status_code == 200
    assert response.json() == {}


def test_get_config_keys():
    """Test /config/keys failure"""
    response = client.get('/config/keys', headers={})

    assert response.status_code == 200
    assert response.json() == configurable_settings()


def test_post_config():
    """Test POST /config endpoint"""
    response = client.post(
        '/config',
        headers={'Content-Type': 'application/json'},
        content=dumps({
            'search_docs_num': '8',
        })
    )
    # update test settings since get_settings.cache_clear() was called
    conftest.update_settings()

    assert response.status_code == 200
    assert response.json() == {'search_docs_num': '8'}


def test_post_config_failure():
    """Test POST /config endpoint"""
    response = client.post(
        '/config',
        headers={'Content-Type': 'application/json'},
        content=dumps({
            'test_key': 'test_value',
        })
    )
    # update test settings since get_settings.cache_clear() was called
    conftest.update_settings()

    assert response.status_code == 400
    assert response.json() == {'detail': 'Setting "test_key" is not configurable'}
