"""API endpoints definitions to handle async jobs"""
from fastapi import APIRouter, HTTPException, status
from brevia.dependencies import get_dependencies
from brevia import async_jobs

router = APIRouter()


@router.get(
    '/jobs/{uuid}',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Analysis'],
)
async def read_analysis_job(uuid: str):
    """
    Read details of a single analisys Job via its UUID
    """
    job = async_jobs.single_job(uuid)
    if job is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Job '{uuid}' was not found",
        )

    return job
