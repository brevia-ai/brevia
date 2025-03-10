"""Providers router module tests"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import patch
from brevia.routers import providers_router

app = FastAPI()
app.include_router(providers_router.router)
client = TestClient(app)


@patch('brevia.routers.providers_router.list_providers')
def test_api_providers(mock_list_providers):
    fake_list = [{
        'model_provider': 'mock_provider', 'models': [{'name': 'mock_model'}]
    }]
    mock_list_providers.return_value = fake_list
    response = client.get('/providers')
    assert response.status_code == 200
    assert response.json() is not None
    assert isinstance(response.json(), list)
    assert response.json() == fake_list
