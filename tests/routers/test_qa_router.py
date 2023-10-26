"""Chat history router tests"""
from fastapi.testclient import TestClient
from fastapi import FastAPI
from langchain.docstore.document import Document
from brevia.routers import qa_router
from brevia.collections import create_collection
from brevia.index import add_document


app = FastAPI()
app.include_router(qa_router.router)
client = TestClient(app)


def test_prompt():
    """Test POST /prompt endpoint"""
    create_collection('test_collection', {})
    response = client.post(
        '/prompt',
        headers={'Content-Type': 'application/json'},
        content='{"question": "How are you?", "collection": "test_collection"}',
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None


def test_search():
    """Test POST /search endpoint"""
    create_collection('test_collection', {})
    add_document(
        document=Document(page_content='Lorem ipsum'),
        collection_name='test_collection',
        document_id='123',
    )
    response = client.post(
        '/search',
        headers={'Content-Type': 'application/json'},
        content='{"query": "How are you?", "collection": "test_collection"}',
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None
