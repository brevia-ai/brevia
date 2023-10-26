"""Collections router tests"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import collections_router
from brevia.collections import create_collection

app = FastAPI()
app.include_router(collections_router.router)
client = TestClient(app)


def test_collections():
    """Test GET /collections endpoint"""
    create_collection('test_collection', {})
    response = client.get('/collections', headers={})
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert len(data) == 1
    assert data[0]['name'] == 'test_collection'


def test_single_collection():
    """Test GET /collections/{uuid} endpoint"""
    collection = create_collection('test_collection', {})
    response = client.get(f'/collections/{collection.uuid}', headers={})
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data['name'] == 'test_collection'


def test_create_collection():
    """Test POST /collections endpoint"""
    response = client.post(
        '/collections',
        headers={'Content-Type': 'application/json'},
        content='{"name": "test_collection", "cmetadata": {}}',
    )
    assert response.status_code == 201
    data = response.json()
    assert data is not None
    assert data['name'] == 'test_collection'


def test_patch_collection():
    """Test PATCH /collections/{id} endpoint"""
    collection = create_collection('test_collection', {})
    response = client.patch(
        f'/collections/{collection.uuid}',
        headers={'Content-Type': 'application/json'},
        content='{"name": "new_collection_name", "cmetadata": {"status": "ok"}}',
    )
    assert response.status_code == 204
    assert response.text == ''


def test_delete_collection():
    """Test DELETE /collections endpoint"""
    collection = create_collection('test_collection', {})
    response = client.delete(
        f'/collections/{collection.uuid}'
    )
    assert response.status_code == 204
    assert response.text == ''
