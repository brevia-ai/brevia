"""Chat history router tests"""
import uuid
import json
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy.orm import Session
from brevia.routers import chat_history_router
from brevia.collections import create_collection
from brevia.connection import db_connection
from brevia.chat_history import add_history, ChatHistoryStore

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


def test_chat_history_sessions():
    """Test /chat_history/sessions success"""
    response = client.get('/chat_history/sessions', headers={})
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert 'data' in data
    assert 'meta' in data
    assert data['data'] == []


def test_evaluate():
    """Test /evaluate endpoint"""
    create_collection('test_collection', {})
    chat_hist = add_history(uuid.uuid4(), 'test_collection', 'who?', 'me')
    evaluation = {
        'uuid': str(chat_hist.uuid),
        'user_evaluation': False,
        'user_feedback': 'Lot of hallucinations!',
        'metadata': {
            'user': 'user_test',
        },
    }
    response = client.post(
        '/evaluate',
        headers={'Content-Type': 'application/json'},
        content=json.dumps(evaluation),
    )
    assert response.status_code == 204

    with Session(db_connection()) as session:
        history_item = session.get(ChatHistoryStore, chat_hist.uuid)
        assert history_item.user_evaluation == evaluation['user_evaluation']
        assert history_item.user_feedback == evaluation['user_feedback']


def test_evaluate_failure():
    """Test /evaluate failure"""
    evaluation = {
        'uuid': str(uuid.uuid4()),
        'user_evaluation': False,
        'user_feedback': 'Lot of hallucinations!',
        'metadata': {
            'user': 'user_test',
        },
    }
    response = client.post(
        '/evaluate',
        headers={'Content-Type': 'application/json'},
        content=json.dumps(evaluation),
    )
    assert response.status_code == 404
