"""load_file module tests"""
from pathlib import Path
import pytest
from brevia.load_file import read, load_documents


def test_read():
    """Test read function"""
    file_path = f'{Path(__file__).parent}/files/docs/empty.pdf'
    content = read(file_path=file_path)
    assert content == 'This is an empty PDF sample file.'

    file_path = f'{Path(__file__).parent}/files/docs/test.txt'
    content = read(file_path=file_path)
    assert content == 'some text'


def test_read_pages():
    """Test read function with page selection"""
    file_path = f'{Path(__file__).parent}/files/docs/empty.pdf'
    content = read(file_path, **{'page_from': 0, 'page_to': 1})
    assert content == 'This is an empty PDF sample file.'


def test_read_failure():
    """Test read function fail"""
    file_path = f'{Path(__file__).parent}/files/silence.mp3'
    with pytest.raises(ValueError) as exc:
        read(file_path=file_path)
    assert str(exc.value) == 'Unsupported file content type "audio/mpeg"'


def test_read_notfound():
    """Test read function fail"""
    file_path = f'{Path(__file__).parent}/files/not.found'
    with pytest.raises(FileNotFoundError) as exc:
        read(file_path=file_path)
    assert str(exc.value) == file_path


def test_load_documents():
    """Test load_documents function"""
    file_path = f'{Path(__file__).parent}/files/docs/empty.pdf'
    docs = load_documents(file_path=file_path)
    assert docs is not None
    assert len(docs) == 1

    file_path = f'{Path(__file__).parent}/files/docs/test.txt'
    docs = load_documents(file_path=file_path)
    assert docs is not None
    assert len(docs) == 1

    file_path = f'{Path(__file__).parent}/files/docs/test.csv'
    docs = load_documents(file_path=file_path)
    assert docs is not None
    assert len(docs) == 1

    file_path = f'{Path(__file__).parent}/files/docs/test.html'
    docs = load_documents(file_path=file_path)
    assert docs is not None
    assert len(docs) == 1


def test_load_documents_fail():
    """Test load_documents failure"""
    file_path = f'{Path(__file__).parent}/files/silence.mp3'
    with pytest.raises(ValueError) as exc:
        read(file_path=file_path)
    assert str(exc.value) == 'Unsupported file content type "audio/mpeg"'
