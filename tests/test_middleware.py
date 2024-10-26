""" Middleware module tests. """
from importlib.metadata import version
import pytest
from fastapi import FastAPI, Response
from brevia.middleware import VersionHeaderMiddleware

pytest_plugins = ('pytest_asyncio',)


@pytest.mark.asyncio
async def test_dispatch():
    """Test dispatch method of VersionHeaderMiddleware class."""
    middleware = VersionHeaderMiddleware(app=FastAPI())

    async def call_next_test(request):
        return Response()

    response = await middleware.dispatch(request=None, call_next=call_next_test)

    assert response.headers.get('X-Brevia-Version') == version('Brevia')
    assert response.headers.get('X-API-Version') is None
    assert response.headers.get('X-API-Name') is None

    middleware = VersionHeaderMiddleware(
        app=FastAPI(),
        api_version='1.0',
        api_name='Test API',
    )

    response = await middleware.dispatch(request=None, call_next=call_next_test)

    assert response.headers.get('X-Brevia-Version') == version('Brevia')
    assert response.headers.get('X-API-Version') == '1.0'
    assert response.headers.get('X-API-Name') == 'Test API'
