""" Event handling for Brevia. """
from fastapi import FastAPI

from brevia.providers import update_providers


def app_events(app: FastAPI) -> None:
    """Add event handlers to FastAPI instance."""
    app.add_event_handler('startup', update_providers)
