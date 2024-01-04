"""API endpoints definitions to handle audio input"""
from typing_extensions import Annotated
from fastapi import APIRouter, Depends
from brevia.dependencies import get_dependencies
from brevia.chat_history import get_history, ChatHistoryFilter

router = APIRouter()


@router.get('/chat_history', dependencies=get_dependencies(json_content_type=False))
def read_chat_history(filter: Annotated[ChatHistoryFilter, Depends()]):
    """ /chat_history endpoint, read stored chat history """
    return get_history(filter=filter)
