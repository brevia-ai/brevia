"""API endpoints definitions to handle document analysis like summarization"""
from typing import Annotated
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
    chain_type: str | None = None
    prompt: dict | None = None
    token_data: bool = False


@router.post('/summarize', dependencies=get_dependencies())
def sum_documents(summarize: SummarizeBody):
    """
    /summarize endpoint:
    Summarize/classification a piece of text

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
    background_tasks: BackgroundTasks,
    chain_type: Annotated[str, Form()] = '',
    prompt: Annotated[str, Form()] = '',
    file: UploadFile | None = None,
    file_content: Annotated[str, Form()] = '',
    token_data: Annotated[bool, Form()] = False,
):
    """
    Upload a PDF file and perform summarization
    See /summarize endpoint for `chain_type`
    arguments
    """
    if file:
        log = logging.getLogger(__name__)
        log.info(f"Uploaded '{file.filename}' - {file.content_type} - {file.size}")
        log.info(f"Chain type '{chain_type}' - token {token_data}")

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
            'chain_type': chain_type,
            'prompt': json.loads(prompt) if prompt else None,
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


def save_base64_tmp_file(file_content: str) -> str:
    """ Save base64 file content to temp file, return path """

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        content_as_bytes = str.encode(file_content)  # convert string to bytes
        content_recovered = b64decode(content_as_bytes)  # decode base64string
        with open(tmp.name, 'wb') as file:
            file.write(content_recovered)

    return str(Path(tmp.name))
