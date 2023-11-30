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
    initial_prompt: dict | None = None
    iteration_prompt: dict | None = None
    token_data: bool = False


@router.post('/summarize', dependencies=get_dependencies())
def sum_documents(summarize: SummarizeBody):
    """
    /summarize endpoint:
    Summarize text and return a summary with algorithm selection
    and custom prompt options.

    Args:
        summarize (SummarizeBody): An object representing the request data
        It contains the following parameters:
            text (str): The text to be summarized
            chain_type: The main langchain summarization chain type should be one of
                "stuff", "map_reduce", and "refine".
                if not providerd stuff is used by default
            initial_prompt: Optional custom prompt to be used in the selected langchain
                chain type to replace the main chain prompt defaults
            iteration_prompt: Optional custom prompts to be used in the selected
                langchain chain type to replace the second chain promopt defaults
            token_data (bool): A boolean indicating whether to include
                token-level data in the summary

    Returns:
        JSON object representing the summary of the provided text

    Raises:
        - HTTPException with status code 400 if the 'text' field is empty

    With this endpoint, you can choose the summarization algorithm from those available
    in the Langchain library and customize the prompts according on the chosen algorithm
    """
    summarize.text = load_file.cleanup_text(summarize.text).strip()
    if not summarize.text:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            'Empty text field',
        )

    service = SummarizeTextService()
    return service.run(summarize.model_dump())


@router.post(
    '/upload_summarize',
    dependencies=get_dependencies(json_content_type=False)
)
def upload_summarize(
    background_tasks: BackgroundTasks,
    chain_type: Annotated[str, Form()] = '',
    initial_prompt: Annotated[str, Form()] = '',
    iteration_prompt: Annotated[str, Form()] = '',
    file: UploadFile | None = None,
    file_content: Annotated[str, Form()] = '',
    token_data: Annotated[bool, Form()] = False,
    payload: Annotated[str, Form()] = '{}',
):
    """
    Upload a PDF file and perform summarization with algorithm
    selection and custom prompt options.

    Args:
        background_tasks (BackgroundTasks): A background task manager
            for handling asynchronous tasks
        chain_type (str, optional): The main Langchain summarization chain type
            Should be one of "stuff", "map_reduce", or "refine"
            If not provided, 'stuff' is used by default
        initial_prompt (str, optional): Optional custom prompt as json string to be
            used in the selected Langchain chain type to replace the main chain
            prompt defaults
        iteration_prompt (str, optional): Optional custom prompt as json string
            to be used in the selected Langchain chain type to replace the second
            chain prompt defaults
        file (UploadFile | None): An uploaded PDF file to be summarized
        file_content (str, optional): Content of the PDF file provided
            as a base64-encoded string
        token_data (bool, optional): A boolean indicating whether to include
            token-level data in the summary
        payload (str, optional): Optional payload in JSON format to use in the async job
            service to add custom options and custom fields

    Returns:
        A JSON object representing the job UUID for the asynchronous summarization task

    Raises:
        HTTPException with status code 400 if either 'file' or 'file_content'
        form field is missing

    With this endpoint, you can upload a PDF file for summarization, select a
    summarization algorithm from those available in the Langchain library,
    and customize the prompts according to your chosen algorithm
    """
    if file:
        log = logging.getLogger(__name__)
        log.info("Uploaded '%s' - %s - %s", file.filename, file.content_type, file.size)
        log.info(
            "Type '%s' - initial prompt: '%s' - iteration prompt: '%s'",
            chain_type,
            initial_prompt,
            iteration_prompt
        )
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
        payload=json.loads(payload) | {
            'file_path': tmp_path,
            'chain_type': chain_type,
            'initial_prompt':
                json.loads(initial_prompt) if initial_prompt else None,
            'iteration_prompt':
                json.loads(iteration_prompt) if iteration_prompt else None,
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
    log.info("Uploaded '%s' - %s - %s", file.filename, file.content_type, file.size)
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
