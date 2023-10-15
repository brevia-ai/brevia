"""Chat history router tests"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import chat_history_router

app = FastAPI()
app.include_router(chat_history_router.router)
client = TestClient(app)


def test_chat_history():
    """Test /chat_history success"""
    response = client.get('/chat_history', headers={})
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert 'data' in data
    assert 'meta' in data
    assert data['data'] == []
