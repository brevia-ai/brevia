"""Events module unit tests."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from brevia.events import app_events
from brevia.providers import update_providers


@pytest.fixture
def app():
    """ FastAPI application"""
    test_app = FastAPI()
    app_events(test_app)
    return test_app


def test_startup_event(app):
    """ Test startup event """
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 404
        # Check if the startup event handler is added
        assert update_providers in app.router.on_startup
