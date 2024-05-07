"""API endpoints definitions to handle audio input"""
import logging
from typing import Annotated
from fastapi import APIRouter, UploadFile, Form
from brevia.models import load_audiotranscriber
from brevia.dependencies import (
    get_dependencies,
    save_upload_file_tmp,
)

router = APIRouter()


@router.post(
    '/transcribe',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Analysis'],
)
def audio_transcriptions(
    file: UploadFile,
    language: Annotated[str, Form()],
):
    """ /transcribe endpoint, audio file transcription """
    log = logging.getLogger(__name__)
    log.info("Uploaded '%s' - %s - %s", file.filename, file.content_type, file.size)
    log.info("Language '%s'", language)
    tmp_file_path = save_upload_file_tmp(file)

    audio = load_audiotranscriber()
    result = audio.transcribe(
        file=tmp_file_path,
        language=language,
    )
    log.info('Audio transcription completed')
    log.info(result)
    return result
