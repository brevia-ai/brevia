"""Events module unit tests."""
from fastapi import FastAPI
from brevia.events import app_events
from brevia.providers import update_providers


def test_startup_event():
    """ Test startup event """
    test_app = FastAPI()
    app_events(test_app)
    assert update_providers in test_app.router.on_startup
