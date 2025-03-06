"""Query module tests"""
import pytest
from langchain.docstore.document import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_core.runnables import Runnable
from brevia.models import load_chatmodel
from brevia.query import (
    conversation_chain,
    create_conversation_retriever,
    search_vector_qa,
    ChatParams,
    SearchQuery,
)
from brevia.collections import create_collection
from brevia.index import add_document
from brevia.settings import get_settings


def test_search_vector_qa():
    """Test search_vector_qa function"""
    with pytest.raises(ValueError) as exc:
        search_vector_qa(search=SearchQuery(query='test', collection='test'))
    assert str(exc.value) == 'Collection not found: test'


def test_search_vector_filter():
    """Test search_vector_qa with metadata filter"""
    create_collection('test', {})
    doc1 = Document(page_content='some', metadata={'category': 'first'})
    add_document(document=doc1, collection_name='test')
    doc2 = Document(page_content='some', metadata={'category': 'second'})
    add_document(document=doc2, collection_name='test')
    doc3 = Document(page_content='some', metadata={})
    add_document(document=doc3, collection_name='test')

    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': 'first'},
    ))
    assert len(result) == 1
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
    ))
    assert len(result) == 3
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': {'$in': ['first', 'second']}},
    ))
    assert len(result) == 2
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': {'$gt': 'first'}},
    ))
    assert len(result) == 1
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': {'$lt': 'first'}},
    ))
    assert len(result) == 0
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'$and': [
            {'category': {'$gte': 'aaaaa'}},
            {'category': {'$lte': 'zzzzz'}},
        ]},
    ))
    assert len(result) == 2
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': {'$ne': 'first'}},
    ))
    assert len(result) == 1


def test_conversation_chain():
    """Test conversation_chain function"""
    collection = create_collection('test', {})
    chain = conversation_chain(collection=collection, chat_params=ChatParams())

    assert chain is not None
    assert isinstance(chain, Runnable)


def test_conversation_retriever():
    """Test create_conversation_retriever function with multiquery"""
    collection = create_collection('test', {})
    retriever = create_conversation_retriever(
        collection=collection,
        chat_params=ChatParams(multiquery=True),
        llm=load_chatmodel({}),
    )

    assert retriever is not None
    assert isinstance(retriever, MultiQueryRetriever)


def test_conversation_custom_retriever():
    """Test create_conversation_retriever with custom retriever"""
    collection = create_collection('test', {})
    settings = get_settings()
    current_retriever = settings.qa_retriever
    conf = {'retriever': 'langchain_core.vectorstores.VectorStoreRetriever'}
    settings.qa_retriever = conf
    retriever = create_conversation_retriever(
        collection=collection,
        chat_params=ChatParams(multiquery=True),
        llm=load_chatmodel({}),
    )

    assert retriever is not None
    assert isinstance(retriever, VectorStoreRetriever)
    settings.qa_retriever = current_retriever

    collection = create_collection('test', {'qa_retriever': conf})
    retriever = create_conversation_retriever(
        collection=collection,
        chat_params=ChatParams(multiquery=True),
        llm=load_chatmodel({}),
    )

    assert retriever is not None
    assert isinstance(retriever, VectorStoreRetriever)
