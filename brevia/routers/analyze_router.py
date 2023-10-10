"""API endpoints definitions to handle document analysis like summarization"""
from typing import Annotated
from os import environ
from base64 import b64decode
from pathlib import Path
import tempfile
import json
import logging
from pydantic import BaseModel
from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    status,
    Request,
    UploadFile,
    Form,
)
from brevia.dependencies import get_dependencies, save_upload_file_tmp
from brevia import async_jobs, load_file
from brevia.services import SummarizeTextService

router = APIRouter()


class SummarizeBody(BaseModel):
    """ summarize input """
    text: str
    summ_prompt: str | None = None
    num_items: int | None = 5
    token_data: bool = False


@router.post('/summarize', dependencies=get_dependencies())
def sum_documents(summarize: SummarizeBody):
    """
    /summarize endpoint:
    Summarize/classification a piece of text

    Specify prompt type:
        - summarize
        - summerize_point
        _ classificate

    num_items:
        - for summarize_point and classificate, specify number of items in output
    """
    summarize.text = load_file.cleanup_text(summarize.text).strip()
    if not summarize.text:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            'Empty text field',
        )

    service = SummarizeTextService()
    return service.run(summarize.dict())


@router.post(
    '/upload_summarize',
    dependencies=get_dependencies(json_content_type=False)
)
def upload_summarize(
    summ_prompt: Annotated[str, Form()],
    background_tasks: BackgroundTasks,
    file: UploadFile | None = None,
    file_content: Annotated[str, Form()] = '',
    num_items: Annotated[str, Form()] = environ.get('SUMM_NUM_ITEMS', '5'),
    token_data: Annotated[bool, Form()] = False,
):
    """
    Upload a PDF file and perform summarization
    See /summarize endpoint for `summ_prompt` and `num_items`
    arguments
    """
    if file:
        log = logging.getLogger(__name__)
        log.info(f"Uploaded '{file.filename}' - {file.content_type} - {file.size}")
        log.info(f"Summ type '{summ_prompt}' - items {num_items} - token {token_data}")
        tmp_path = save_upload_file_tmp(file)
    elif file_content:
        tmp_path = save_base64_tmp_file(file_content=file_content)
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            'One of "file" or "file_content" form field is mandatory',
        )

    job = async_jobs.create_job(
        service='brevia.services.SummarizeFileService',
        payload={
            'file_path': tmp_path,
            'summ_prompt': summ_prompt,
            'num_items': int(num_items),
            'token_data': token_data,
        }
    )
    background_tasks.add_task(async_jobs.run_job_service, job.uuid)

    return {'job': job.uuid}


@router.post('/upload_analyze', dependencies=get_dependencies(json_content_type=False))
def upload_analyze(
    file: UploadFile,
    service: Annotated[str, Form()],
    background_tasks: BackgroundTasks,
    payload: Annotated[str, Form()] = '{}',
):
    """
    Upload a file and perform some analysis using a `service` class
    """
    log = logging.getLogger(__name__)
    log.info(f"Uploaded '{file.filename}' - {file.content_type} - {file.size}")
    tmp_path = save_upload_file_tmp(file)

    payload = json.loads(payload)
    payload['file_path'] = tmp_path
    job = async_jobs.create_job(
        service=service,
        payload=payload,
    )
    background_tasks.add_task(async_jobs.run_job_service, job.uuid)

    return {'job': job.uuid}


@router.post(
    '/summarize_binary',
    dependencies=get_dependencies(json_content_type=False)
)
async def summarize_binary(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Perform summarization of a PDF file
    passed via binary POST (application/octet-stream)
    """
    body: bytes = await request.body()
    tmp_file_path = save_binary_tmp_file(file_content=body)

    job = async_jobs.create_job(
        service='brevia.services.SummarizeFileService',
        payload={'file_path': tmp_file_path},
    )
    background_tasks.add_task(async_jobs.run_job_service, job.uuid)

    return {'job': job.uuid}


def save_binary_tmp_file(file_content: bytes) -> str:
    """ Save binary content to temp file, return path """
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        with open(tmp.name, 'wb') as file:
            file.write(file_content)

    return str(Path(tmp.name))


def save_base64_tmp_file(file_content: str) -> str:
    """ Save base64 file content to temp file, return path """

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        content_as_bytes = str.encode(file_content)  # convert string to bytes
        content_recovered = b64decode(content_as_bytes)  # decode base64string
        with open(tmp.name, 'wb') as file:
            file.write(content_recovered)

    return str(Path(tmp.name))
