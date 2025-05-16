"""Download files endpoint."""
import os
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from brevia.settings import get_settings


router = APIRouter()


@router.api_route(
    '/download/{file_path:path}',
    methods=['GET', 'HEAD'],
    tags=['Download'],
)
async def download_file(file_path: str):
    """
    Endpoint to download a file from the internal file system.
    """
    base_path = get_settings().file_output_base_path
    # Check if the base path is an S3 file path
    if base_path.startswith('s3://'):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            'File download is not supported',
        )

    full_path = os.path.join(base_path, file_path)
    if not os.path.isfile(full_path):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f'File not found: {file_path}',
        )

    return FileResponse(full_path, filename=os.path.basename(full_path))
