"""API endpoints for question answering and search"""
from typing import Annotated
import asyncio
from langchain.callbacks import AsyncIteratorCallbackHandler, get_openai_callback
from langchain.callbacks.openai_info import OpenAICallbackHandler
from langchain.chains.base import Chain
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from brevia import query, chat_history
from brevia.dependencies import (
    get_dependencies,
    check_collection_name,
)
from brevia.callback import ConversationCallbackHandler
# from brevia.language import Detector
from brevia.models import test_models_in_use

router = APIRouter()


class PromptBody(BaseModel):
    """ /prompt request body """
    question: str
    collection: str
    chat_history: list = []
    docs_num: int | None = None
    streaming: bool = False
    distance_strategy_name: str | None = None
    source_docs: bool = False
    token_data: bool = False


@router.post('/prompt', dependencies=get_dependencies())
async def prompt_action(
    prompt: PromptBody,
    x_chat_session: Annotated[str | None, Header()] = None,
):
    """ /prompt endpoint, ask chatbot about a collection of documents """
    collection = check_collection_name(prompt.collection)
    if not collection.cmetadata:
        collection.cmetadata = dict()
    # langDetector = Detector()
    # lang = langDetector.detect(prompt.question)
    lang = ''  # restore previous lines after https://github.com/brevia-ai/brevia/pull/8

    conversation_handler = ConversationCallbackHandler()
    stream_handler = AsyncIteratorCallbackHandler()
    chain = query.conversation_chain(
        collection=collection,
        docs_num=prompt.docs_num,
        streaming=prompt.streaming,
        answer_callbacks=[stream_handler] if prompt.streaming else [],
        conversation_callbacks=[conversation_handler]
    )

    if not prompt.streaming or test_models_in_use():
        return await run_chain(
            chain=chain,
            prompt=prompt,
            lang=lang,
            x_chat_session=x_chat_session,
        )

    asyncio.create_task(run_chain(
        chain=chain,
        prompt=prompt,
        lang=lang,
        x_chat_session=x_chat_session,
    ))

    async def event_generator(
        stream_callback: AsyncIteratorCallbackHandler,
        conversation_callback: ConversationCallbackHandler,
        source_docs: bool = False,
    ):
        ait = stream_callback.aiter()

        async for token in ait:
            yield token

        if not source_docs:
            yield ''
        else:
            await conversation_callback.wait_conversation_done()

            yield conversation_callback.chain_result()

    return StreamingResponse(event_generator(
        stream_callback=stream_handler,
        conversation_callback=conversation_handler,
        source_docs=prompt.source_docs,
    ))


def prompt_chat_history(history: list, question: str, session: str = None) -> list:
    """Retrieve chat history to be used in final prompt creation"""
    chat_hist = chat_history.history(
        chat_history=history,
        session=session,
    )
    if chat_hist and not chat_history.is_related(chat_hist, question):
        chat_hist = []

    return chat_hist


async def run_chain(
    chain: Chain,
    prompt: PromptBody,
    lang: str,
    x_chat_session: str,
):
    """Run chain usign async methods and return result"""
    with get_openai_callback() as callb:
        result = await chain.acall({
            'question': prompt.question,
            'chat_history': prompt_chat_history(
                history=prompt.chat_history,
                question=prompt.question,
                session=x_chat_session,
            ),
            'lang': lang,
        })

    return prompt_result(
        result=result,
        callb=callb,
        prompt=prompt,
        x_chat_session=x_chat_session
    )


def prompt_result(
    result: dict,
    callb: OpenAICallbackHandler,
    prompt: PromptBody,
    x_chat_session: str | None = None,
) -> dict:
    """ Handle prompt result: save chat history and return answer """
    answer = result['answer'].strip(" \n")

    chat_history.add_history(
            session_id=x_chat_session,
            collection=prompt.collection,
            question=prompt.question,
            answer=answer,
            metadata=callb.__dict__,
    )

    return {
        'bot': answer,
        'docs': None if not prompt.source_docs else result['source_documents'],
        'token_data': None if not prompt.token_data else callb.__dict__
    }


class SearchBody(BaseModel):
    """ /search request body """
    query: str
    collection: str
    docs_num: int | None = None
    distance_strategy_name: str | None = None


@router.post('/search', dependencies=get_dependencies())
def search_documents(search: SearchBody):
    """
        /search endpoint:
        Search the first {docs_num} relevant documents for a question

        Specify distance_strategy:
            EUCLIDEAN = EmbeddingStore.embedding.l2_distance (default)
            COSINE = EmbeddingStore.embedding.cosine_distance
            MAX_INNER_PRODUCT = EmbeddingStore.embedding.max_inner_product
    """
    check_collection_name(search.collection)

    params = {k: v for k, v in search.dict().items() if v is not None}
    result = query.search_vector_qa(**params)

    return extract_content_score(result)


def extract_content_score(data_list) -> list:
    """Extract score from search result list."""

    if 'error' in data_list:
        return {'error': data_list['error']}
    extracted_data = []
    for item in data_list:
        content = item[0].page_content.strip(" \n")
        score = item[1]
        extracted_data.append({"content": content, "score": score})
    return extracted_data
