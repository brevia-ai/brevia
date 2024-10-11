"""Settings module tests"""
from os import environ
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


def test_setup_environment():
    """Test setup_environment method"""
    environ.pop('OPENAI_API_KEY', None)
    environ.pop('COHERE_API_KEY', None)
    settings = Settings()
    settings.openai_api_key = 'fakefakefake'
    settings.cohere_api_key = 'fakefakefake'
    settings.brevia_env_secrets = {}
    settings.setup_environment()
    assert environ.get('OPENAI_API_KEY') is not None
    assert environ.get('COHERE_API_KEY') is not None

    environ.pop('OPENAI_API_KEY', None)
    environ.pop('COHERE_API_KEY', None)
    settings.openai_api_key = None
    settings.cohere_api_key = None
    settings.brevia_env_secrets = {}
    settings.setup_environment()
    assert environ.get('OPENAI_API_KEY') is None
    assert environ.get('COHERE_API_KEY') is None


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
    """Test get_settings method"""
    new_conf = {'test_key': 'test_value', 'search_docs_num': '7'}
    conf = update_db_conf(db_connection(), new_conf)
    assert 'test_key' not in conf
    assert conf['search_docs_num'] == '7'


def test_get_settings_db():
    """Test get_settings with configuration from DB"""
    new_conf = {'test_key': 'test_value', 'search_docs_num': '7'}
    update_db_conf(db_connection(), new_conf)

    # current search_docs_num
    current = get_settings().search_docs_num

    get_settings.cache_clear()
    conftest.update_settings()

    settings = get_settings()
    assert 'test_key' not in settings
    assert settings.search_docs_num == 7

    # restore defaults
    settings.search_docs_num = current
