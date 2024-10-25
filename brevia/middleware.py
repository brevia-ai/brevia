from importlib.metadata import version
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """Middleware to add version headers to response"""
    def __init__(
        self,
        app: ASGIApp,
        brevia_version: str | None = None,
        api_version: str | None = None,
    ) -> None:
        super().__init__(app)
        self.brevia_version = brevia_version
        self.api_version = api_version

    async def dispatch(self, request, call_next):
        """Add version header to response"""
        response = await call_next(request)
        if self.brevia_version:
            response.headers['X-Brevia-Version'] = self.brevia_version
        else:
            response.headers['X-Brevia-Version'] = version('Brevia')
        if self.api_version:
            response.headers['X-API-Version'] = self.api_version

        return response
