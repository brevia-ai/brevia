"""Status router tests"""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import analyze_router
from brevia import models

app = FastAPI()
app.include_router(analyze_router.router)
client = TestClient(app)


def test_summarize():
    """Test POST /summarize"""
    response = client.post(
        '/summarize',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'text': 'Lorem Ipsum',
        })
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data == {
        'output': models.LOREM_IPSUM,
        'token_data': None
    }


def test_upload_summarize():
    """Test POST /upload_summarize"""
    test_path = Path(__file__).parent.parent
    file_path = f'{test_path}/files/empty.pdf'
    handle = open(file_path, 'rb')
    with TestClient(app) as client:
        response = client.post(
            '/upload_summarize',
            files={'file': handle},
            data={'summ_prompt': 'summarize'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data['job'] is not None
