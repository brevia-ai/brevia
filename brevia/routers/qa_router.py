"""API endpoints for question answering and search"""
from typing import Annotated
import asyncio
from langchain.callbacks import AsyncIteratorCallbackHandler
from langchain.chains.base import Chain
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from brevia import chat_history
from brevia.dependencies import (
    get_dependencies,
    check_collection_name,
)
from brevia.callback import (
    ConversationCallbackHandler,
    token_usage_callback,
    token_usage,
    TokensCallbackHandler,
)
from brevia.language import Detector
from brevia.query import SearchQuery, ChatParams, conversation_chain, search_vector_qa
from brevia.models import test_models_in_use

router = APIRouter()


class ChatBody(ChatParams):
    """ /chat request body """
    question: str
    collection: str
    chat_history: list = []
    chat_lang: str | None = None
    token_data: bool = False


@router.post('/prompt', dependencies=get_dependencies(), deprecated=True, tags=['Chat'])
@router.post('/chat', dependencies=get_dependencies(), tags=['Chat'])
async def chat_action(
    chat_body: ChatBody,
    x_chat_session: Annotated[str | None, Header()] = None,
):
    """ /chat endpoint, ask chatbot about a collection of documents """
    collection = check_collection_name(chat_body.collection)
    if not collection.cmetadata:
        collection.cmetadata = {}
    lang = chat_language(chat_body=chat_body, cmetadata=collection.cmetadata)

    conversation_handler = ConversationCallbackHandler()
    stream_handler = AsyncIteratorCallbackHandler()
    chain = conversation_chain(
        collection=collection,
        chat_params=ChatParams(**chat_body.model_dump()),
        answer_callbacks=[stream_handler] if chat_body.streaming else [],
        conversation_callbacks=[conversation_handler]
    )

    if not chat_body.streaming or test_models_in_use():
        return await run_chain(
            chain=chain,
            chat_body=chat_body,
            lang=lang,
            x_chat_session=x_chat_session,
        )

    asyncio.create_task(run_chain(
        chain=chain,
        chat_body=chat_body,
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
        source_docs=chat_body.source_docs,
    ))


def chat_language(chat_body: ChatBody, cmetadata: dict) -> str:
    """Retrieve the language to be used in Q/A response"""
    chat_lang = chat_body.chat_lang or cmetadata.get('chat_lang')
    if chat_lang:
        return chat_lang

    return Detector().detect(chat_body.question)


def retrieve_chat_history(history: list, question: str, session: str = None) -> list:
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
    chat_body: ChatBody,
    lang: str,
    x_chat_session: str,
):
    """Run chain usign async methods and return result"""
    with token_usage_callback() as callb:
        result = await chain.acall({
            'question': chat_body.question,
            'chat_history': retrieve_chat_history(
                history=chat_body.chat_history,
                question=chat_body.question,
                session=x_chat_session,
            ),
            'lang': lang,
        })

    return chat_result(
        result=result,
        callb=callb,
        chat_body=chat_body,
        x_chat_session=x_chat_session
    )


def chat_result(
    result: dict,
    callb: TokensCallbackHandler,
    chat_body: ChatBody,
    x_chat_session: str | None = None,
) -> dict:
    """ Handle chat result: save chat history and return answer """
    answer = result['answer'].strip(" \n")

    chat_history.add_history(
            session_id=x_chat_session,
            collection=chat_body.collection,
            question=chat_body.question,
            answer=answer,
            metadata=token_usage(callb),
    )

    return {
        'bot': answer,
        'docs': None if not chat_body.source_docs else result['source_documents'],
        'token_data': None if not chat_body.token_data else token_usage(callb)
    }


@router.post('/search', dependencies=get_dependencies(), tags=['Index'])
def search_documents(search: SearchQuery):
    """
        /search endpoint:
        Search the first {docs_num} relevant documents for a question

        Specify distance_strategy:
            EUCLIDEAN = EmbeddingStore.embedding.l2_distance (default)
            COSINE = EmbeddingStore.embedding.cosine_distance
            MAX_INNER_PRODUCT = EmbeddingStore.embedding.max_inner_product
    """
    collection = check_collection_name(search.collection)
    if search.docs_num is None and 'docs_num' in collection.cmetadata:
        search.docs_num = int(collection.cmetadata['docs_num'])
    result = search_vector_qa(search=search)

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
