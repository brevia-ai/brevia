"""Status router tests"""
from json import dumps
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.connection import db_connection
from brevia.routers import config_router
from brevia.settings import get_configurable_keys, get_settings, update_db_conf
from tests import conftest

app = FastAPI()
app.include_router(config_router.router)
client = TestClient(app)


def test_get_config():
    """Test /config endpoint"""
    response = client.get('/config', headers={})
    assert response.status_code == 200
    assert response.json() == get_settings().model_dump()


def test_get_config_key():
    """Test /config endpoint with key query parameter"""
    response = client.get('/config?key=search_docs_num&key=text_chunk_size', headers={})
    assert response.status_code == 200
    assert response.json() == {
        'search_docs_num': get_settings().search_docs_num,
        'text_chunk_size': get_settings().text_chunk_size,
    }


def test_get_config_key_failure():
    """Test /config endpoint with key query parameter failure"""
    response = client.get('/config?key=invalid_key', headers={})
    assert response.status_code == 400
    assert response.json() == {
        'detail': 'There are not configurable settings: invalid_key'
    }


def test_get_config_schema():
    """Test /config/schema endpoint"""
    response = client.get('/config/schema', headers={})

    assert response.status_code == 200
    schema = response.json()
    assert 'properties' in schema
    keys = get_configurable_keys()
    assert all(key in schema['properties'] for key in keys)


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


def test_post_config_reset():
    """Test POST /config/reset endpoint"""
    current = get_settings().search_docs_num
    update_db_conf(db_connection(), {'search_docs_num': '18'})
    conftest.update_settings()
    assert get_settings().search_docs_num == 18

    response = client.post(
        '/config/reset',
        headers={'Content-Type': 'application/json'},
        content=dumps(['search_docs_num'])
    )
    # update test settings since get_settings.cache_clear() was called
    conftest.update_settings()
    assert get_settings().search_docs_num == current

    assert response.status_code == 200
    assert response.json() == {}
