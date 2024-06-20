"""API endpoints definitions to handle audio input"""
from typing_extensions import Annotated
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from brevia.dependencies import get_dependencies
from brevia.chat_history import (
    get_history,
    get_history_sessions,
    history_evaluation,
    ChatHistoryFilter,
)

router = APIRouter()


@router.get(
    '/chat_history',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Chat'],
)
def read_chat_history(filter: Annotated[ChatHistoryFilter, Depends()]):
    """ /chat_history endpoint, read stored chat history """
    return get_history(filter=filter)


@router.get(
    '/chat_history/sessions',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Chat'],
)
def read_chat_history_sessions(filter: Annotated[ChatHistoryFilter, Depends()]):
    """ /chat_history sessions endpoint, read stored chat history sessions"""
    return get_history_sessions(filter=filter)


class EvaluateBody(BaseModel):
    """ Evaluation creation model """
    uuid: str
    user_evaluation: bool
    user_feedback: str | None = None
    metadata: dict | None = None


@router.post(
    '/evaluate',
    status_code=204,
    dependencies=get_dependencies(),
    tags=['Chat'],
)
def evluate_chat_history(body: EvaluateBody):
    """ /evaluate endpoint, save chat history item user evaluation """
    result = history_evaluation(
        history_id=body.uuid,
        user_evaluation=body.user_evaluation,
        user_feedback=body.user_feedback,
        metadata=body.metadata,
    )
    if not result:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Chat history '{body.uuid}' was not found",
        )
