"""Index router tests"""
import json
from uuid import uuid4
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import index_router
from brevia.collections import create_collection

app = FastAPI()
app.include_router(index_router.router)
client = TestClient(app)


def test_create_index_document():
    """Test POST /index endpoint"""
    collection = create_collection('test_collection', {})
    response = client.post(
        '/index',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'content': 'Lorem Ipsum',
            'collection_id': str(collection.uuid),
            'document_id': '123',
        })
    )
    assert response.status_code == 204
    assert response.text == ''


def test_create_index_failure():
    """Test POST /index failure"""
    response = client.post(
        '/index',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'content': 'Lorem Ipsum',
            'collection_id': str(uuid4()),
            'document_id': '123',
        })
    )
    assert response.status_code == 404


def test_get_index_document():
    """Test GET /index/{collection_id}/{document_id} endpoint"""
    collection = create_collection('test_collection', {})
    response = client.post(
        '/index',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'content': 'Lorem Ipsum',
            'collection_id': str(collection.uuid),
            'document_id': '123',
        })
    )
    assert response.status_code == 204
    assert response.text == ''

    response = client.get(f'/index/{collection.uuid}/123', headers={})
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data == [{'document': 'Lorem Ipsum', 'cmetadata': {}}]


def test_delete_document_index():
    """Test DELETE /index/{collection_id}/{document_id} endpoint"""
    collection = create_collection('test_collection', {})
    response = client.post(
        '/index',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'content': 'Lorem Ipsum',
            'collection_id': str(collection.uuid),
            'document_id': '123',
        })
    )
    assert response.status_code == 204
    assert response.text == ''

    response = client.delete(
        f'/index/{collection.uuid}/123'
    )
    assert response.status_code == 204
    assert response.text == ''


def test_upload_analyze():
    """Test POST /index/upload"""
    collection = create_collection('test_collection', {})
    file_path = f'{Path(__file__).parent.parent}/files/docs/empty.pdf'
    response = client.post(
        '/index/upload',
        files={'file': open(file_path, 'rb')},
        data={
            'collection_id': str(collection.uuid),
            'document_id': '1234',
        },
    )
    assert response.status_code == 204
    assert response.text == ''


def test_upload_analyze_meta():
    """Test POST /index/upload with metadata"""
    collection = create_collection('test_collection', {})
    file_path = f'{Path(__file__).parent.parent}/files/docs/empty.pdf'
    response = client.post(
        '/index/upload',
        files={'file': open(file_path, 'rb')},
        data={
            'collection_id': str(collection.uuid),
            'document_id': '1234',
            'metadata': '{"category":"something"}',
        },
    )
    assert response.status_code == 204
    assert response.text == ''


def test_upload_analyze_fail():
    """Test POST /index/upload failure"""
    collection = create_collection('test_collection', {})
    file_path = f'{Path(__file__).parent.parent}/files/silence.mp3'
    response = client.post(
        '/index/upload',
        files={'file': open(file_path, 'rb')},
        data={
            'collection_id': str(collection.uuid),
            'document_id': '1234',
        },
    )
    assert response.status_code == 400
