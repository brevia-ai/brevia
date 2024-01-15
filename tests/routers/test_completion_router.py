"""Complerions router tests"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers.completion_router import router


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_completion():
    """Test POST /completion endpoint"""
    response = client.post(
        '/completion',
        headers={'Content-Type': 'application/json'},
        content='{"text": "test", "prompt": {"_type": "prompt","input_variables": ["text"],"template": "test"} }',
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None


