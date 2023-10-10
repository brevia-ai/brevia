"""API endpoints definitions to handle audio input"""
import logging
from os import environ
from typing import Annotated
from fastapi import APIRouter, UploadFile, Form
import openai
from brevia.dependencies import (
    get_dependencies,
    save_upload_file_tmp,
)

router = APIRouter()


@router.post(
    '/transcribe',
    dependencies=get_dependencies(json_content_type=False)
)
def audio_transcriptions(
    file: UploadFile,
    language: Annotated[str, Form()],
):
    """ /transcribe endpoint, audio file transcription """
    log = logging.getLogger(__name__)
    log.info(f"Uploaded '{file.filename}' - {file.content_type} - {file.size}")
    log.info(f"Language '{language}")
    tmp_file_path = save_upload_file_tmp(file)

    with open(tmp_file_path, 'rb') as audio_file:

        result = openai.Audio.transcribe(
                model='whisper-1',
                file=audio_file,
                api_key=environ.get('OPENAI_API_KEY'),
                params={'language': language},
        )
        log.info('Audio transcription completed')
        log.info(result)
        return result
