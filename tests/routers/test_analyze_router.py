"""Status router tests"""
import json
from pathlib import Path
from base64 import b64encode
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import analyze_router
from brevia import models
from brevia.async_jobs import single_job

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
        'token_data': {}
    }


def test_summarize_fail():
    """Test POST /summarize fail"""
    response = client.post(
        '/summarize',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({'text': ''})
    )
    assert response.status_code == 400


def test_upload_summarize():
    """Test POST /upload_summarize"""
    test_path = Path(__file__).parent.parent
    file_path = f'{test_path}/files/docs/empty.pdf'
    handle = open(file_path, 'rb')
    response = client.post(
        '/upload_summarize',
        files={'file': handle},
        data={
            'chain_type': 'map_reduce',
            'payload': '{"custom_field":"custom_value"}'
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data['job'] is not None
    job = single_job(data['job'])
    assert job is not None
    assert job.payload.get('chain_type') == 'map_reduce'
    assert job.payload.get('custom_field') == 'custom_value'


def test_upload_summarize_fail():
    """Test POST /upload_summarize fail"""
    response = client.post(
        '/upload_summarize',
        data={'chain_type': 'gustavo'},
    )
    assert response.status_code == 400


def test_upload_summarize_base64():
    """Test POST /upload_summarize with base64 string"""
    text = 'Lorem Ipsum'
    response = client.post(
        '/upload_summarize',
        data={
            'chain_type': 'stuff',
            'file_content': b64encode(text.encode())
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data['job'] is not None


def test_upload_analyze():
    """Test POST /upload_analyze"""
    test_path = Path(__file__).parent.parent
    file_path = f'{test_path}/files/docs/empty.pdf'
    handle = open(file_path, 'rb')
    response = client.post(
        '/upload_analyze',
        files={'file': handle},
        data={'service': 'brevia.services.FakeService'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data['job'] is not None
