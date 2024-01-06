"""App metadata module tests"""
from pathlib import Path
from brevia.settings import get_settings
from brevia.app_metadata import metadata


def test_metadata():
    """Test metadata method"""
    meta = metadata(f'{Path(__file__).parent.parent}/pyproject.toml')
    assert list(meta.keys()) == ['title', 'description', 'version', 'openapi_tags']
    assert meta['version'] != 'unknown'


def test_metadata_block():
    """Test blocked urls"""
    settings = get_settings()
    settings.block_openapi_urls = True
    meta = metadata('pyproject.toml')
    assert meta == {'docs_url': None, 'redoc_url': None}
    settings.block_openapi_urls = False


def test_metadata_err():
    """Test matadata error"""
    meta = metadata('notexisting.toml')
    assert list(meta.keys()) == ['title', 'description', 'version', 'openapi_tags']
    assert meta['version'] == 'unknown'
