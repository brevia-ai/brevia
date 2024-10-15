"""Status router tests"""
from json import dumps
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import config_router
from brevia.settings import configurable_settings, get_settings
from tests import conftest

app = FastAPI()
app.include_router(config_router.router)
client = TestClient(app)


def test_get_config():
    """Test /config endpoint"""
    response = client.get('/config', headers={})
    assert response.status_code == 200
    assert response.json() == {}


def test_get_config_schema():
    """Test /config/schema endpoint"""
    response = client.get('/config/schema', headers={})

    assert response.status_code == 200
    schema = response.json()
    assert 'properties' in schema
    assert all(key in schema['properties'] for key in configurable_settings())


def test_post_config():
    """Test POST /config endpoint"""
    current = get_settings().search_docs_num
    response = client.post(
        '/config',
        headers={'Content-Type': 'application/json'},
        content=dumps({
            'search_docs_num': '8',
        })
    )
    # update test settings since get_settings.cache_clear() was called
    conftest.update_settings()
    assert get_settings().search_docs_num == 8
    get_settings().search_docs_num = current

    assert response.status_code == 200
    assert response.json() == {'search_docs_num': '8'}


def test_post_config_extra_failure():
    """Test POST /config endpoint failure"""
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
    assert response.json() == {
        'detail': 'There are not configurable settings: test_key'
    }


def test_post_config_invalid_failure():
    """Test POST /config endpoint failure"""
    response = client.post(
        '/config',
        headers={'Content-Type': 'application/json'},
        content=dumps({
            'search_docs_num': 'gustavo',
        })
    )
    # update test settings since get_settings.cache_clear() was called
    conftest.update_settings()

    assert response.status_code == 400
    assert 'detail' in response.json()
    detail = response.json()['detail']
    assert 'search_docs_num' in detail
    assert 'gustavo' in detail
