"""Index module tests"""
from pathlib import Path
import pytest
from brevia.index import load_pdf_file
from brevia.collections import create_collection


def test_load_pdf_file():
    """Test load_pdf_file method"""
    collection = create_collection('test_collection', {})
    file_path = f'{Path(__file__).parent}/files/empty.pdf'
    result = load_pdf_file(file_path=file_path, collection_name=collection.name)
    assert result == 1


def test_load_pdf_file_fail():
    """Test load_pdf_file failure"""
    file_path = f'{Path(__file__).parent}/files/notfound.pdf'
    with pytest.raises(FileNotFoundError) as exc:
        load_pdf_file(file_path=file_path, collection_name='test')
    assert str(exc.value) == file_path
