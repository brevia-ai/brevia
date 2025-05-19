"""Output utility module tests."""
import os
import pytest
from unittest.mock import patch, MagicMock
from brevia.settings import get_settings
from brevia.utilities.output import PublicFileOutput


@pytest.fixture
def mock_settings():
    """Fixture to mock the get_settings function."""
    with patch("brevia.utilities.output.get_settings") as mock_get_settings:
        mock_get_settings.return_value.file_output_base_path = '/tmp'
        mock_get_settings.return_value.file_output_base_url = 'http://localhost/files'
        yield mock_get_settings


def test_file_path_local():
    """Test file_path method for local file paths."""
    output = PublicFileOutput(job_id='1234')
    filename = 'test.txt'

    file_path = output.file_path(filename)
    assert file_path == get_settings().file_output_base_path + '/1234/test.txt'


def test_file_path_s3(mock_settings):
    """Test file_path method for S3 paths."""
    mock_settings.return_value.file_output_base_path = 's3://my-bucket'
    output = PublicFileOutput(job_id='1234')
    filename = 'test.txt'

    file_path = output.file_path(filename)
    assert file_path is not None
    assert not file_path.startswith(get_settings().file_output_base_path)

    parent_dir = os.path.dirname(file_path)
    os.rmdir(parent_dir)


def test_file_url():
    """Test file_url method."""
    output = PublicFileOutput()
    file_url = output.file_url('test.txt')

    assert file_url == '/download/test.txt'


def test_write_local_file():
    """Test write method for local file writing."""
    output = PublicFileOutput(job_id='1234')
    filename = 'test2.txt'
    content = 'Hello, World!'

    url = output.write(content, filename)
    assert url == '/download/1234/test2.txt'
    os.remove(output.file_path(filename))


@patch('brevia.utilities.output.PublicFileOutput._s3_upload')
def test_write_s3_file(mock_s3_upload):
    """Test write method for S3 file writing."""
    mock_s3_upload.return_value = None
    output = PublicFileOutput(job_id='1234')
    filename = 'test2.txt'
    content = 'Hello, S3!'

    file_url = output.write(content, filename)
    assert file_url == '/download/1234/test2.txt'


# @patch('brevia.utilities.output.get_settings')
def test_s3_upload_method():
    """Test the _s3_upload method."""
    output = PublicFileOutput(job_id='1234')

    mock_s3 = MagicMock()
    import sys
    sys.modules['boto3'] = mock_s3
    mock_client = MagicMock()
    mock_s3.client.return_value = mock_client
    mock_client.upload_file.return_value = None

    result = output._s3_upload('test.txt', 'my-bucket', '1234/test.txt')
    assert result is None
