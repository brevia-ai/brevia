"""Query module tests"""
import pytest
from langchain.docstore.document import Document
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.messages.ai import AIMessage
from langchain_core.runnables import Runnable
from brevia.models import load_chatmodel
from brevia.query import (
    conversation_chain,
    conversation_rag_chain,
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
    """Test simple conversation_chain function without collection"""
    chain = conversation_chain(chat_params=ChatParams())
    assert chain is not None
    assert isinstance(chain, Runnable)

    # Test with streaming enabled
    chain = conversation_chain(
        chat_params=ChatParams(streaming=True),
        answer_callbacks=[],
    )
    assert chain is not None
    assert isinstance(chain, Runnable)


def test_conversation_chain_output():
    """Test conversation_chain output format"""
    chain = conversation_chain(chat_params=ChatParams())
    result = chain.invoke({
        'question': 'What is 2+2?',
        'chat_history': [],
        'lang': '',
    })

    assert isinstance(result, AIMessage)
    assert hasattr(result, 'content')
    assert isinstance(result.content, str)
    assert len(result.content) > 0


def test_conversation_rag_chain():
    """Test RAG-based conversation_rag_chain function"""
    collection = create_collection('test', {})
    chain = conversation_rag_chain(
        collection=collection,
        chat_params=ChatParams(),
    )
    assert chain is not None
    assert isinstance(chain, Runnable)

    # Test with streaming enabled
    chain = conversation_rag_chain(
        collection=collection,
        chat_params=ChatParams(streaming=True),
        answer_callbacks=[],
    )
    assert chain is not None
    assert isinstance(chain, Runnable)


def test_conversation_rag_chain_with_docs():
    """Test conversation_rag_chain with documents and query"""
    collection = create_collection('test', {})
    doc = Document(page_content='The answer to life is 42', metadata={})
    add_document(document=doc, collection_name='test')

    chain = conversation_rag_chain(
        collection=collection,
        chat_params=ChatParams(source_docs=True),
    )

    result = chain.invoke({
        'question': 'What is the answer to life?',
        'chat_history': [],
        'lang': '',
    })

    assert isinstance(result, dict)
    assert 'answer' in result
    assert 'context' in result
    assert isinstance(result['answer'], str)
    assert isinstance(result['context'], list)


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
