"""API endpoints definitions to handle audio input"""
from fastapi import APIRouter
from brevia.dependencies import get_dependencies
from brevia import chat_history

router = APIRouter()


@router.get('/chat_history', dependencies=get_dependencies(json_content_type=False))
def read_chat_history(
    max_date: str | None = None,
    collection: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    """ /chat_history endpoint, read stored chat history """
    return chat_history.get_history(
        max_date=max_date,
        collection=collection,
        page=page,
        page_size=page_size,
    )
