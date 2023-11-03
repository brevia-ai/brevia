"""files_import module tests"""
from pathlib import Path
import pytest
from brevia.utilities.files_import import index_file_folder
from brevia.collections import create_collection


def test_index_file_folder():
    """Test index_file_folder function"""
    create_collection('empty', {})
    folder_path = f'{Path(__file__).parent.parent}/files/docs'
    result = index_file_folder(file_path=folder_path, collection='empty')
    assert result == 3


def test_index_file_folder_fail():
    """Test index_file_folder failure"""
    with pytest.raises(FileNotFoundError) as exc:
        index_file_folder(file_path='/not/found', collection='test')
    assert str(exc.value) == "File /not/found does not exist."
