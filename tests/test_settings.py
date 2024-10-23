"""Settings module tests"""
from os import environ
import pytest
from sqlalchemy.orm import Session
from brevia.connection import db_connection
from brevia.settings import (
    Settings,
    ConfigStore,
    get_settings,
    read_db_conf,
    update_db_conf,
)
from tests import conftest


def test_brevia_env_secrets():
    """Test setup_environment with brevia_env_secrets var"""
    environ.pop('TEST_TOKEN', None)
    settings = Settings()
    settings.setup_environment()
    assert environ.get('TEST_TOKEN') is None

    environ.pop('TEST_TOKEN', None)
    settings = Settings()
    settings.brevia_env_secrets = {'TEST_TOKEN': 'abcd'}
    settings.setup_environment()
    assert environ.get('TEST_TOKEN') is not None
    environ.pop('TEST_TOKEN', None)


def test_connection_string():
    """Test connection_string method"""
    current = get_settings().pgvector_dsn_uri
    test_dsn_uri = 'postgresql+driver://user:password@host:port/database'
    settings = get_settings()
    settings.pgvector_dsn_uri = test_dsn_uri
    assert settings.connection_string() == test_dsn_uri
    # restore previous setting
    settings.pgvector_dsn_uri = current


def test_read_db_conf():
    """Test read_db_conf method"""
    with Session(db_connection()) as session:
        session.add(ConfigStore(config_key='test_key', config_val='test_value'))
        session.add(ConfigStore(config_key='search_docs_num', config_val='7'))
        session.commit()

    conf = read_db_conf(db_connection())
    assert 'test_key' not in conf
    assert conf['search_docs_num'] == '7'


def test_update_db_conf():
    """Test update_db_conf method"""
    new_conf = {'test_key': 'test_value', 'search_docs_num': '7'}
    conf = update_db_conf(db_connection(), new_conf)
    # update test settings since get_settings.cache_clear() was called
    conftest.update_settings()
    assert 'test_key' not in conf
    assert conf['search_docs_num'] == '7'


def test_update_db_conf_failure():
    """Test update_db_conf failure"""
    new_conf = {'search_docs_num': 'wrong value'}
    with pytest.raises(ValueError) as exc:
        update_db_conf(db_connection(), new_conf)

    assert 'search_docs_num' in str(exc.value)
    assert 'wrong value' in str(exc.value)


def test_get_settings_db():
    """Test get_settings with configuration from DB"""
    # current settings values
    current_doc_num = get_settings().search_docs_num
    current_chunk_size = get_settings().text_chunk_size

    new_conf = {'test_k': 'test_v', 'text_chunk_size': '4567', 'search_docs_num': '8'}
    result = update_db_conf(db_connection(), new_conf)
    # update test settings since get_settings.cache_clear() was called
    conftest.update_settings()
    assert result == {'text_chunk_size': '4567', 'search_docs_num': '8'}

    new_conf = {'search_docs_num': '7'}
    result = update_db_conf(db_connection(), new_conf)
    conftest.update_settings()
    assert result == {'text_chunk_size': '4567', 'search_docs_num': '7'}

    settings = get_settings()
    assert 'test_key' not in settings
    assert settings.search_docs_num == 7

    # restore defaults
    settings.search_docs_num = current_doc_num
    settings.text_chunk_size = current_chunk_size
