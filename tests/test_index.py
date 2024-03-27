"""Index module tests"""
from pathlib import Path
import pytest
from brevia.index import (
    load_pdf_file, update_links_documents,
    add_document, document_has_changed, select_load_link_options
)
from brevia.collections import create_collection
from langchain.docstore.document import Document


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


def test_select_load_link_options():
    """Test select_load_link_options method"""
    options = [{'url': 'example.com', 'selector': 'test'}]
    result = select_load_link_options(url='example.com', options=options)
    assert result == {'selector': 'test'}

    result = select_load_link_options(url='example.com/somepath', options=options)
    assert result == {'selector': 'test'}

    result = select_load_link_options(url='someurl.org', options=options)
    assert result == {}
