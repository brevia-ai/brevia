"""Index router tests"""
import json
from uuid import uuid4
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from langchain.docstore.document import Document
from brevia.routers import index_router
from brevia.collections_tools import create_collection
from brevia.index import add_document, read_document
from unittest.mock import patch

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
    assert data == [{'document': 'Lorem Ipsum', 'cmetadata': {'part': 1}}]


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


@patch('brevia.routers.index_router.load_file.requests.get')
def test_index_link(mock_get):
    """Test POST /index/link endpoint"""
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = 'Lorem Ipsum'
    collection = create_collection('test_collection', {})
    response = client.post(
        '/index/link',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'link': 'https://www.example.com',
            'collection_id': str(collection.uuid),
            'document_id': '123',
            'metadata': {'type': 'links'},
        })
    )
    assert response.status_code == 204
    assert response.text == ''
    docs = read_document(collection_id=str(collection.uuid), document_id='123')
    assert len(docs) == 1
    assert docs[0].get('cmetadata') == {'type': 'links', 'part': 1}
    assert docs[0].get('document') == 'Lorem Ipsum'


@patch('brevia.routers.index_router.load_file.requests.get')
def test_index_link_callback(mock_get):
    """Test POST /index/link endpoint with 'callback' option filter"""
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = '<h1> lorem ipsum</h1>'
    collection = create_collection('test_collection', {})
    response = client.post(
        '/index/link',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'link': 'https://www.example.com',
            'collection_id': str(collection.uuid),
            'document_id': '123',
            'metadata': {'type': 'links'},
            'options': {'callback': 'string.capwords'},
        })
    )
    assert response.status_code == 204
    assert response.text == ''
    docs = read_document(collection_id=str(collection.uuid), document_id='123')
    assert len(docs) == 1
    assert docs[0].get('cmetadata') == {'type': 'links', 'part': 1}
    assert docs[0].get('document') == 'Lorem Ipsum'


@patch('brevia.routers.index_router.load_file.requests.get')
def test_index_link_callback_fail(mock_get):
    """Test POST /index/link endpoint with 'callback' option failure"""
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = '<h1>Lorem ipsum</h1>'
    collection = create_collection('test_collection', {})
    with pytest.raises(ValueError) as exc:
        client.post(
            '/index/link',
            headers={'Content-Type': 'application/json'},
            content=json.dumps({
                'link': 'https://www.example.com',
                'collection_id': str(collection.uuid),
                'document_id': '123',
                'options': {'callback': 'brevia.index.zzzzzz'},
            })
        )
        assert str(exc.value) == 'Callback "brevia.index.zzzzzz" not found'


@patch('brevia.routers.index_router.load_file.requests.get')
def test_index_link_selector(mock_get):
    """Test POST /index/link endpoint with 'selector' option filter"""
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = '<h1>Lorem Ipsum</h1><p class="test">Some text</p>'
    collection = create_collection('test_collection', {})
    response = client.post(
        '/index/link',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'link': 'https://www.example.com',
            'collection_id': str(collection.uuid),
            'document_id': '123',
            'metadata': {'type': 'links'},
            'options': {'selector': 'p.test'},
        })
    )
    assert response.status_code == 204
    assert response.text == ''
    docs = read_document(collection_id=str(collection.uuid), document_id='123')
    assert len(docs) == 1
    assert docs[0].get('cmetadata') == {'type': 'links', 'part': 1}
    assert docs[0].get('document') == 'Some text'


@patch('brevia.routers.index_router.load_file.requests.get')
def test_index_link_metadata_options(mock_get):
    """Test POST /index/link endpoint using collection metadata options"""
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = '<h1>lorem ipsum</h1><p class="test"> any text </p>'
    opts = {'link_load_options': [
        {
            'url': 'https://www.example.com',
            'selector': 'p.test',
        },
        {
            'url': 'https://www.example.com/some/page',
            'callback': 'string.capwords',
        }
    ]}
    collection = create_collection('test_collection', opts)
    response = client.post(
        '/index/link',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'link': 'https://www.example.com/some/page',
            'collection_id': str(collection.uuid),
            'document_id': '123',
            'metadata': {'type': 'links'},
        })
    )
    assert response.status_code == 204
    assert response.text == ''
    docs = read_document(collection_id=str(collection.uuid), document_id='123')
    assert len(docs) == 1
    assert docs[0].get('cmetadata') == {'type': 'links', 'part': 1}
    assert docs[0].get('document') == 'Any Text'


@patch('brevia.routers.index_router.load_file.requests.get')
def test_index_link_empty(mock_get):
    """Test POST /index/link endpoint with empty or missing response"""
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = ''
    collection = create_collection('test_collection', {})
    response = client.post(
        '/index/link',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'link': 'https://www.example.com',
            'collection_id': str(collection.uuid),
            'document_id': '123',
            'metadata': {'type': 'links'},
        })
    )
    assert response.status_code == 204
    assert response.text == ''
    docs = read_document(collection_id=str(collection.uuid), document_id='123')
    assert len(docs) == 0


def test_index_metadata_document():
    """Test POST /index/metadata endpoint"""
    collection = create_collection('test_collection', {})
    doc1 = Document(page_content='some', metadata={'category': 'first'})
    add_document(document=doc1, collection_name='test_collection', document_id='123')
    response = client.post(
        '/index/metadata',
        headers={'Content-Type': 'application/json'},
        content=json.dumps({
            'collection_id': str(collection.uuid),
            'document_id': '123',
            'metadata': {'category': 'second'},
        })
    )
    assert response.status_code == 204
    assert response.text == ''
    docs = read_document(collection_id=str(collection.uuid), document_id='123')
    assert len(docs) == 1
    assert docs[0].get('cmetadata') == {'category': 'second'}


def test_get_index_collection():
    """Test GET /index/{collection_id} endpoint with filter query string"""
    collection = create_collection('test_collection', {})

    doc1 = Document(page_content='Lorem Ipsum', metadata={'type': 'documents'})
    add_document(document=doc1, collection_name='test_collection', document_id='123')
    doc2 = Document(page_content='Dolor Sit', metadata={'type': 'questions'})
    add_document(document=doc2, collection_name='test_collection', document_id='456')

    response = client.get(f'/index/{collection.uuid}?filter[type]=documents')
    assert response.status_code == 200
    data = response.json()
    assert 'data' in data
    assert data['data'] == [{
        'document': 'Lorem Ipsum',
        'cmetadata': {'type': 'documents', 'part': 1},
        'custom_id': '123'
    }]


def test_get_index_collection_failure():
    """Test GET /index/{collection_id} endpoint with bad argument"""
    response = client.get('/index/gustavo')
    assert response.status_code == 404


def test_get_index_documents_metadata():
    """Test GET /index/{collection_id}/documents_metadata endpoint"""
    collection = create_collection('test_collection', {})

    doc1 = Document(page_content='Lorem Ipsum', metadata={'type': 'documents'})
    add_document(document=doc1, collection_name='test_collection', document_id='123')
    doc2 = Document(page_content='Dolor Sit', metadata={'type': 'questions'})
    add_document(document=doc2, collection_name='test_collection', document_id='456')

    response = client.get(f'/index/{collection.uuid}/documents_metadata')
    assert response.status_code == 200
    data = response.json()
    assert data == [
        {
            'cmetadata': {'type': 'documents', 'part': 1},
            'custom_id': '123'
        },
        {
            'cmetadata': {'type': 'questions', 'part': 1},
            'custom_id': '456'
        },
    ]

    query = 'filter[type]=questions'
    response = client.get(f'/index/{collection.uuid}/documents_metadata?{query}')
    assert response.status_code == 200
    data = response.json()
    assert data == [{
        'cmetadata': {'type': 'questions', 'part': 1},
        'custom_id': '456'
    }]

    query = 'document_id=123'
    response = client.get(f'/index/{collection.uuid}/documents_metadata?{query}')
    assert response.status_code == 200
    data = response.json()
    assert data == [{
        'cmetadata': {'type': 'documents', 'part': 1},
        'custom_id': '123'
    }]
