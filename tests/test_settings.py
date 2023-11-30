"""Settings module tests"""
from os import environ
from brevia.settings import Settings


def test_setup_environment():
    """Test _setup_environment method"""
    del environ['OPENAI_API_KEY']
    settings = Settings()
    settings.setup_environment()
    assert environ.get('OPENAI_API_KEY') is not None

    del environ['OPENAI_API_KEY']
    settings.openai_api_key = None
    settings.setup_environment()
    assert environ.get('OPENAI_API_KEY') is None
