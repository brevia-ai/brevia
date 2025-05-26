"""Download Router module tests."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import FastAPI, status
from brevia.routers.download_router import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_download_file_success():
    """Test download file success."""
    response = client.get('/download/silence.mp3')
    assert response.status_code == status.HTTP_200_OK


def test_download_file_not_found():
    """Test download file not found."""
    response = client.get('/download/nonexistent_file.txt')
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'File not found: nonexistent_file.txt'}


@patch('brevia.routers.download_router.get_settings')
def test_download_file_s3_path(mock_get_settings):
    """Test download file from S3 path."""
    mock_get_settings.return_value.file_output_base_path = 's3://mock-bucket'

    response = client.get('/download/test_file.txt')
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'File download is not supported'}
