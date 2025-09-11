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

    output = LinkedFileOutput(job_id='123456789')
    file_url = output.file_url('test.txt')

    assert file_url == '/download/123456789/test.txt'


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
    mock_client = MagicMock()
    mock_s3.client.return_value = mock_client
    mock_client.upload_file.return_value = None

    with patch.dict('sys.modules', {'boto3': mock_s3}):
        result = output._s3_upload('test.txt', 'my-bucket', '1234/test.txt')
        assert result is None


def test_cleanup_job_files_no_job_id():
    """Test cleanup_job_files raises ValueError when no job_id is set."""
    output = LinkedFileOutput()

    with pytest.raises(ValueError) as exc:
        output.cleanup_job_files()
    assert "No job_id set" in str(exc.value)


@patch("brevia.utilities.output.get_settings")
@patch("os.path.exists")
@patch("os.path.isdir")
@patch("shutil.rmtree")
def test_cleanup_job_files_local(mock_rmtree, mock_isdir, mock_exists, mock_settings):
    """Test cleanup_job_files method for local filesystem."""
    mock_settings.return_value.file_output_base_path = '/tmp'
    mock_exists.return_value = True
    mock_isdir.return_value = True

    output = LinkedFileOutput(job_id='1234')
    output.cleanup_job_files()

    mock_exists.assert_called_once_with('/tmp/1234')
    mock_isdir.assert_called_once_with('/tmp/1234')
    mock_rmtree.assert_called_once_with('/tmp/1234')


@patch("brevia.utilities.output.get_settings")
@patch("os.path.exists")
def test_cleanup_job_files_local_no_directory(mock_exists, mock_settings):
    """Test cleanup_job_files method when local directory doesn't exist."""
    mock_settings.return_value.file_output_base_path = '/tmp'
    mock_exists.return_value = False

    output = LinkedFileOutput(job_id='1234')
    # Should not raise an error if directory doesn't exist
    output.cleanup_job_files()

    mock_exists.assert_called_once_with('/tmp/1234')


@patch('brevia.utilities.output.LinkedFileOutput._s3_delete_objects')
@patch("brevia.utilities.output.get_settings")
def test_cleanup_job_files_s3(mock_settings, mock_s3_delete):
    """Test cleanup_job_files method for S3 storage."""
    mock_settings.return_value.file_output_base_path = 's3://my-bucket'
    mock_s3_delete.return_value = None

    output = LinkedFileOutput(job_id='1234')
    output.cleanup_job_files()

    mock_s3_delete.assert_called_once_with('my-bucket', '1234/')


@patch('brevia.utilities.output.LinkedFileOutput._s3_delete_objects')
@patch("brevia.utilities.output.get_settings")
def test_cleanup_job_files_s3_with_prefix(mock_settings, mock_s3_delete):
    """Test cleanup_job_files method for S3 storage with base prefix."""
    mock_settings.return_value.file_output_base_path = 's3://my-bucket/output/files'
    mock_s3_delete.return_value = None

    output = LinkedFileOutput(job_id='1234')
    output.cleanup_job_files()

    mock_s3_delete.assert_called_once_with('my-bucket', 'output/files/1234/')


def test_s3_delete_objects_import_error():
    """Test the _s3_delete_objects method for ImportError."""
    output = LinkedFileOutput(job_id='1234')

    # Mock the import to raise ModuleNotFoundError
    with patch('builtins.__import__') as mock_import:
        def side_effect(name, *args):
            if name == 'boto3':
                raise ModuleNotFoundError("No module named 'boto3'")
            return __import__(name, *args)

        mock_import.side_effect = side_effect

        with pytest.raises(ImportError) as exc:
            output._s3_delete_objects('my-bucket', '1234/')
        assert str(exc.value) == 'Boto3 is not installed!'


def test_s3_delete_objects_method():
    """Test the _s3_delete_objects method."""
    output = LinkedFileOutput(job_id='1234')

    mock_s3 = MagicMock()
    mock_client = MagicMock()
    mock_s3.client.return_value = mock_client

    # Mock the list_objects_v2 response
    mock_client.list_objects_v2.return_value = {
        'Contents': [
            {'Key': '1234/file1.txt'},
            {'Key': '1234/file2.txt'},
            {'Key': '1234/subdir/file3.txt'}
        ]
    }
    mock_client.delete_objects.return_value = None

    with patch.dict('sys.modules', {'boto3': mock_s3}):
        output._s3_delete_objects('my-bucket', '1234/')

        mock_client.list_objects_v2.assert_called_once_with(
            Bucket='my-bucket', Prefix='1234/'
        )
        mock_client.delete_objects.assert_called_once_with(
            Bucket='my-bucket',
            Delete={
                'Objects': [
                    {'Key': '1234/file1.txt'},
                    {'Key': '1234/file2.txt'},
                    {'Key': '1234/subdir/file3.txt'}
                ]
            }
        )


def test_s3_delete_objects_no_contents():
    """Test the _s3_delete_objects method when no objects are found."""
    output = LinkedFileOutput(job_id='1234')

    mock_s3 = MagicMock()
    mock_client = MagicMock()
    mock_s3.client.return_value = mock_client

    # Mock the list_objects_v2 response with no contents
    mock_client.list_objects_v2.return_value = {}

    with patch.dict('sys.modules', {'boto3': mock_s3}):
        # Should not raise an error when no objects are found
        output._s3_delete_objects('my-bucket', '1234/')

        mock_client.list_objects_v2.assert_called_once_with(
            Bucket='my-bucket', Prefix='1234/'
        )
        mock_client.delete_objects.assert_not_called()


def test_s3_delete_objects_large_batch():
    """Test the _s3_delete_objects method with more than 1000 objects."""
    output = LinkedFileOutput(job_id='1234')

    mock_s3 = MagicMock()
    mock_client = MagicMock()
    mock_s3.client.return_value = mock_client

    # Create a list with more than 1000 objects
    objects = [{'Key': f'1234/file{i}.txt'} for i in range(1500)]
    mock_client.list_objects_v2.return_value = {'Contents': objects}
    mock_client.delete_objects.return_value = None

    with patch.dict('sys.modules', {'boto3': mock_s3}):
        output._s3_delete_objects('my-bucket', '1234/')

        # Should be called twice due to 1000 object limit per batch
        assert mock_client.delete_objects.call_count == 2

        # First call should have 1000 objects
        first_call_args = mock_client.delete_objects.call_args_list[0]
        assert len(first_call_args[1]['Delete']['Objects']) == 1000

        # Second call should have remaining 500 objects
        second_call_args = mock_client.delete_objects.call_args_list[1]
        assert len(second_call_args[1]['Delete']['Objects']) == 500
