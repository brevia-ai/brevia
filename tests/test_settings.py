"""Settings module tests"""
from os import environ
from brevia.settings import Settings


def test_setup_environment():
    """Test setup_environment method"""
    environ.pop('OPENAI_API_KEY', None)
    environ.pop('COHERE_API_KEY', None)
    settings = Settings()
    settings.openai_api_key = 'fakefakefake'
    settings.cohere_api_key = 'fakefakefake'
    settings.setup_environment()
    assert environ.get('OPENAI_API_KEY') is not None
    assert environ.get('COHERE_API_KEY') is not None

    environ.pop('OPENAI_API_KEY', None)
    environ.pop('COHERE_API_KEY', None)
    settings.openai_api_key = None
    settings.cohere_api_key = None
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
