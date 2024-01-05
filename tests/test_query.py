"""Query module tests"""
import pytest
from langchain.prompts import BasePromptTemplate
from langchain.chains import ConversationalRetrievalChain
from langchain.docstore.document import Document
from brevia.query import (
    conversation_chain,
    load_qa_prompt,
    load_condense_prompt,
    search_vector_qa,
    ChatParams,
    SearchQuery,
)
from brevia.collections import create_collection
from brevia.index import add_document

FAKE_PROMPT = {
    '_type': 'prompt',
    'input_variables': [],
    'template': 'Fake',
}


def test_load_qa_prompt():
    """Test load_qa_prompt method"""
    result = load_qa_prompt({
        'system': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

    result = load_qa_prompt({
        'human': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)


def test_load_condense_prompt():
    """Test load_condense_prompt method"""
    result = load_condense_prompt({
        'few': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

    result = load_condense_prompt({
        'condense': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)


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
        filter={'category': {'in': ['first', 'second']}},
    ))
    assert len(result) == 2
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': {'gt': 'first'}},
    ))
    assert len(result) == 1
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': {'lt': 'first'}},
    ))
    assert len(result) == 0
    # 'GE' and 'LE' operators not yet supported
    # result = search_vector_qa(search=SearchQuery(
    #     query='test',
    #     collection='test',
    #     filter={'category': {'ge': 'aaaaa', 'le': 'zzzzz'}},
    # ))
    # assert len(result) == 2
    result = search_vector_qa(search=SearchQuery(
        query='test',
        collection='test',
        filter={'category': {'ne': 'first'}},
    ))
    assert len(result) == 1


def test_conversation_chain():
    """Test conversation_chain function"""
    collection = create_collection('test', {})
    chain = conversation_chain(collection=collection, chat_params=ChatParams())

    assert chain is not None
    assert isinstance(chain, ConversationalRetrievalChain)
