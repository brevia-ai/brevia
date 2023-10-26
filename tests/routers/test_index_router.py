"""Chat history router tests"""
import json
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
