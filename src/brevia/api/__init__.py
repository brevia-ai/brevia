"""HTTP API of Brevia: :func:`create_app` builds a FastAPI app with its endpoints.

The endpoints of an application, added to the same app, receive the Brevia of the app
and the caller of the request with :data:`BreviaDep` and :data:`CallerDep`.
"""

from .app import create_app
from .requests import BreviaDep, CallerDep

__all__ = ["BreviaDep", "CallerDep", "create_app"]
