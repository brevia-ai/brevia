"""API endpoints definitions to handle async jobs"""
from typing_extensions import Annotated
from fastapi import APIRouter, HTTPException, status, Depends
from brevia.dependencies import get_dependencies
from brevia.async_jobs import get_jobs, single_job, JobsFilter

router = APIRouter()


@router.get(
    '/jobs/{uuid}',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Analysis', 'Jobs'],
)
async def read_analysis_job(uuid: str):
    """
    Read details of a single analisys Job via its UUID
    """
    job = single_job(uuid)
    if job is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Job '{uuid}' was not found",
        )

    return job


@router.get(
    '/jobs',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Jobs'],
)
async def list_analysis_jobs(filter: Annotated[JobsFilter, Depends()]):
    """ /jobs endpoint, list all analysis jobs """
    return get_jobs(filter=filter)
