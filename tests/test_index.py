"""Index module tests"""
from pathlib import Path
from unittest.mock import patch
from h11 import Response
from langchain_text_splitters import NLTKTextSplitter
from langchain_text_splitters.character import RecursiveCharacterTextSplitter
import pytest
from requests import HTTPError
from langchain.docstore.document import Document
from brevia.index import (
    load_pdf_file, split_document, update_links_documents,
    add_document, document_has_changed, select_load_link_options,
    documents_metadata, create_splitter,
)
from brevia.collections import create_collection
from brevia.settings import get_settings


def test_load_pdf_file():
    """Test load_pdf_file method"""
    collection = create_collection('test_collection', {})
    file_path = f'{Path(__file__).parent}/files/docs/empty.pdf'
    result = load_pdf_file(file_path=file_path, collection_name=collection.name)
    assert result == 1


def test_load_pdf_file_fail():
    """Test load_pdf_file failure"""
    file_path = f'{Path(__file__).parent}/files/notfound.pdf'
    with pytest.raises(FileNotFoundError) as exc:
        load_pdf_file(file_path=file_path, collection_name='test')
    assert str(exc.value) == file_path


def test_update_links_documents():
    """Test update_links_documents method with zero results"""
    result = update_links_documents('test')
    assert result == 0

    create_collection('test', {})
    doc1 = Document(page_content='some', metadata={'type': 'links'})
    add_document(document=doc1, collection_name='test')
    result = update_links_documents('test')
    assert result == 0


def test_document_has_changed():
    """Test document_has_changed method"""
    collection = create_collection('test', {})

    doc1 = Document(page_content='some', metadata={})
    add_document(document=doc1, collection_name='test', document_id='1')
    result = document_has_changed(doc1, collection.uuid, '1')
    assert result is False

    doc1.metadata = {'type': 'links'}
    result = document_has_changed(doc1, collection.uuid, '1')
    assert result is True

    add_document(document=Document(page_content='another'),
                 collection_name='test', document_id='1')
    result = document_has_changed(doc1, collection.uuid, '1')
    assert result is True


def _raise_http_err():
    raise HTTPError('404 Client Error', response=Response(headers=[], status_code=404))


@patch('brevia.index.load_file.requests.get')
def test_update_links_documents_http_error(mock_get):
    """Test update_links_documents method with HTTP error"""
    collection = create_collection('test', {})
    doc1 = Document(
        page_content='some', metadata={'type': 'links', 'url': 'http://example.com'}
    )
    add_document(document=doc1, collection_name='test', document_id='1')

    mock_get.return_value.status_code = 404
    mock_get.return_value.text = '404 Client Error'
    mock_get.return_value.raise_for_status = _raise_http_err

    result = update_links_documents('test')
    assert result == 0
    meta = documents_metadata(collection_id=collection.uuid, document_id='1')
    assert meta[0]['cmetadata']['http_error'] == '404'

    mock_get.return_value.status_code = 200
    mock_get.return_value.text = 'changed'

    def donothing():
        pass
    mock_get.return_value.raise_for_status = donothing

    result = update_links_documents('test')
    assert result == 1
    meta = documents_metadata(collection_id=collection.uuid, document_id='1')
    assert meta[0]['cmetadata'].get('http_error') is None


def test_select_load_link_options():
    """Test select_load_link_options method"""
    options = [
        {'url': 'example.com', 'selector': 'test'},
        {'url': 'example.com/some', 'selector': 'test2'},
        {'url': 'example.com/other', 'other': 'value'}
    ]
    result = select_load_link_options(url='example.com/other', options=options)
    assert result == {'selector': 'test', 'other': 'value'}

    result = select_load_link_options(url='example.com/some', options=options)
    assert result == {'selector': 'test2', 'other': None}

    result = select_load_link_options(url='someurl.org', options=options)
    assert result == {'selector': None, 'other': None}


def test_custom_split():
    """Test split_documents method with custom splitter class"""
    doc1 = Document(page_content='some content? no', metadata={'type': 'questions'})
    cls = 'langchain_text_splitters.character.RecursiveCharacterTextSplitter'
    texts = split_document(doc1, {'splitter': cls})

    assert len(texts) == 1


def test_add_document_custom_split():
    """Test add_document method with custom splitter in settings"""
    settings = get_settings()
    current_splitter = settings.text_splitter
    settings.text_splitter = {
        'splitter': 'langchain_text_splitters.character.RecursiveCharacterTextSplitter'
    }
    doc1 = Document(page_content='some content? no', metadata={'type': 'questions'})
    num = add_document(document=doc1, collection_name='test')
    assert num == 1

    settings.text_splitter = current_splitter


def test_create_splitter_chunk_params():
    """Test create_splitter method"""
    splitter = create_splitter({'chunk_size': 2222, 'chunk_overlap': 333})

    assert isinstance(splitter, NLTKTextSplitter)
    assert splitter._chunk_size == 2222
    assert splitter._chunk_overlap == 333

    splitter = create_splitter({})

    assert isinstance(splitter, NLTKTextSplitter)
    assert splitter._chunk_size == get_settings().text_chunk_size
    assert splitter._chunk_overlap == get_settings().text_chunk_overlap

    custom_splitter = {
        'splitter': 'langchain_text_splitters.character.RecursiveCharacterTextSplitter',
        'chunk_size': 1111,
        'chunk_overlap': 555,
    }
    splitter = create_splitter({
        'chunk_size': 3333,
        'chunk_overlap': 444,
        'text_splitter': custom_splitter,
    })

    assert isinstance(splitter, RecursiveCharacterTextSplitter)
    assert splitter._chunk_size == 1111
    assert splitter._chunk_overlap == 555
