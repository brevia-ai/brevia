"""Brevia Middleware classes"""
from importlib.metadata import version
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """Middleware to add version headers to response"""
    def __init__(
        self,
        app: ASGIApp,
        api_version: str = '',
        api_name: str = '',
    ) -> None:
        super().__init__(app)
        self.api_version = api_version
        self.api_name = api_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Add version header to response"""
        response = await call_next(request)
        response.headers['X-Brevia-Version'] = version('Brevia')
        # Add API version and name headers
        # about the custom API created with Brevia
        if self.api_name:
            response.headers['X-API-Name'] = self.api_name
        if self.api_version:
            response.headers['X-API-Version'] = self.api_version

        return response
