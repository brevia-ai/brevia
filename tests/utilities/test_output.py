"""Output utility module tests."""
import os
import pytest
from unittest.mock import patch, MagicMock
from brevia.settings import get_settings
from brevia.utilities.output import LinkedFileOutput


@pytest.fixture
def mock_settings():
    """Fixture to mock the get_settings function."""
    with patch("brevia.utilities.output.get_settings") as mock_get_settings:
        mock_get_settings.return_value.file_output_base_path = '/tmp'
        mock_get_settings.return_value.file_output_base_url = 'http://localhost/files'
        yield mock_get_settings


def test_file_path_local():
    """Test file_path method for local file paths."""
    output = LinkedFileOutput(job_id='1234')
    filename = 'test.txt'

    file_path = output.file_path(filename)
    assert file_path == get_settings().file_output_base_path + '/1234/test.txt'


def test_file_path_s3(mock_settings):
    """Test file_path method for S3 paths."""
    mock_settings.return_value.file_output_base_path = 's3://my-bucket'
    output = LinkedFileOutput(job_id='1234')
    filename = 'test.txt'

    file_path = output.file_path(filename)
    assert file_path is not None
    assert not file_path.startswith(get_settings().file_output_base_path)


def test_file_url():
    """Test file_url method."""
    output = LinkedFileOutput()
    file_url = output.file_url('test.txt')

    assert file_url == '/download/test.txt'


def test_write_local_file():
    """Test write method for local file writing."""
    output = LinkedFileOutput(job_id='1234')
    filename = 'test2.txt'
    content = 'Hello, World!'

    url = output.write(content, filename)
    assert url == '/download/1234/test2.txt'
    os.unlink(output.file_path(filename))


@patch('brevia.utilities.output.LinkedFileOutput._s3_upload')
@patch("brevia.utilities.output.get_settings")
def test_write_s3_file(mock_settings, mock_s3_upload):
    """Test write method for S3 file writing."""
    mock_settings.return_value.file_output_base_path = 's3://my-bucket'
    mock_settings.return_value.file_output_base_url = 'https://my-bucket.s3aws.com'
    mock_s3_upload.return_value = None
    output = LinkedFileOutput(job_id='1234')
    filename = 'test2.txt'
    content = 'Hello, S3!'

    file_url = output.write(content, filename)
    assert file_url == 'https://my-bucket.s3aws.com/1234/test2.txt'


def test_s3_upload_import_error():
    """Test the _s3_upload method for ImportError."""
    output = LinkedFileOutput(job_id='1234')

    with pytest.raises(ImportError) as exc:
        output._s3_upload('test.txt', 'my-bucket', '1234/test.txt')
    assert str(exc.value) == 'Boto3 is not installed!'


def test_s3_upload_method():
    """Test the _s3_upload method."""
    output = LinkedFileOutput(job_id='1234')

    mock_s3 = MagicMock()
    import sys
    sys.modules['boto3'] = mock_s3
    mock_client = MagicMock()
    mock_s3.client.return_value = mock_client
    mock_client.upload_file.return_value = None

    result = output._s3_upload('test.txt', 'my-bucket', '1234/test.txt')
    assert result is None
