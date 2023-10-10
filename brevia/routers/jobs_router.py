"""API endpoints definitions to handle async jobs"""
from fastapi import APIRouter, HTTPException, status
from brevia.dependencies import get_dependencies
from brevia import async_jobs

router = APIRouter()


@router.get('/jobs/{uuid}', dependencies=get_dependencies(json_content_type=False))
async def read_collection(uuid: str):
    """ /jobs/{uuid} endpoint"""
    job = async_jobs.single_job(uuid)
    if job is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Job '{uuid}' was not found",
        )

    return job
