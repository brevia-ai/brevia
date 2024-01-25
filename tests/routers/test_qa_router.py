"""Q/A router tests"""
from json import dumps
from fastapi.testclient import TestClient
from fastapi import FastAPI
from langchain.docstore.document import Document
from brevia.routers.qa_router import (
    router, ChatBody, chat_language, retrieve_chat_history, extract_content_score
)
from brevia.collections import create_collection
from brevia.index import add_document
from brevia.settings import get_settings


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_chat():
    """Test POST /chat endpoint"""
    create_collection('test_collection', {})
    response = client.post(
        '/chat',
        headers={'Content-Type': 'application/json'},
        content='{"question": "How are you?", "collection": "test_collection"}',
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None


def test_chat_filter():
    """Test POST /chat with metadata filter"""
    create_collection('test_collection', {})
    doc1 = Document(page_content='some', metadata={'category': 'first'})
    add_document(document=doc1, collection_name='test_collection')
    doc2 = Document(page_content='some', metadata={'category': 'second'})
    add_document(document=doc2, collection_name='test_collection')

    body = {
        'question': 'How?',
        'collection': 'test_collection',
        'filter': {'category': {'in': ['first', 'third']}},
    }
    response = client.post(
        '/chat',
        headers={'Content-Type': 'application/json'},
        content=dumps(body),
    )
    assert response.status_code == 200
    data = response.json()
    assert data is not None


def test_search():
    """Test POST /search endpoint"""
    create_collection('test_collection', {'docs_num': 3})
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


def test_search_filter():
    """Test POST /search with metadata filter"""
    create_collection('test_collection', {})
    doc1 = Document(page_content='some', metadata={'category': 'first'})
    add_document(document=doc1, collection_name='test_collection')
    doc2 = Document(page_content='some', metadata={'category': 'second'})
    add_document(document=doc2, collection_name='test_collection')

    body = {
        'query': 'How?',
        'collection': 'test_collection',
        'filter': {'category': 'first'},
    }
    response = client.post(
        '/search',
        headers={'Content-Type': 'application/json'},
        content=dumps(body),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_chat_language():
    """Test chat_language method"""
    chat_body = ChatBody(question='', collection='', chat_lang='Klingon')
    lang = chat_language(chat_body=chat_body, cmetadata={})
    assert lang == 'Klingon'


def test_retrieve_chat_history():
    """Test retrieve_chat_history method"""
    settings = get_settings()
    thresh = settings.qa_followup_sim_threshold
    settings.qa_followup_sim_threshold = 100
    history = [{'query': 'a', 'answer': 'b'}]
    chat_hist = retrieve_chat_history(history=history, question='c')
    assert len(chat_hist) == 0
    # restore threshold
    settings.qa_followup_sim_threshold = thresh


def test_extract_content_score():
    """Test extract_content_score method"""
    result = extract_content_score(data_list={'error': 'big problems!'})
    assert result == {'error': 'big problems!'}
