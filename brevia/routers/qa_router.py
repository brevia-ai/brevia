"""API endpoints for question answering and search"""
import asyncio
from typing import Annotated
from typing_extensions import Self
from glom import glom
from pydantic import Field, model_validator
from langchain.callbacks import AsyncIteratorCallbackHandler
from langchain.chains.base import Chain
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages.ai import AIMessage
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
from brevia.query import (
    SearchQuery,
    ChatParams,
    conversation_chain,
    conversation_rag_chain,
    search_vector_qa,
)
from brevia.models import test_models_in_use

router = APIRouter()


class ChatBody(ChatParams):
    """ /chat request body """
    question: str
    collection: str | None = None
    chat_history: list = []
    chat_lang: str | None = None
    config: dict | None = None
    mode: str = Field(pattern='^(rag|conversation)$', default='rag')
    token_data: bool = False

    @model_validator(mode='after')
    def check_collection(self) -> Self:
        """Validate collection and mode"""
        if not self.collection and self.mode == 'rag':
            raise ValueError('Collection required for rag mode')
        return self


@router.post('/prompt', dependencies=get_dependencies(), deprecated=True, tags=['Chat'])
@router.post('/chat', dependencies=get_dependencies(), tags=['Chat'])
async def chat_action(
    chat_body: ChatBody,
    x_chat_session: Annotated[str | None, Header()] = None,
):
    """
    /chat endpoint, ask chatbot about a collection of documents to perform a rag chat.
    If collection is not provided, it will use a simple completion chain.
    """
    # Check if collection is provided and valid
    collection = None
    if chat_body.collection:
        collection = check_collection_name(chat_body.collection)
        if not collection.cmetadata:
            collection.cmetadata = {}

    lang = chat_language(
        chat_body=chat_body,
        cmetadata=collection.cmetadata if collection else {}
    )
    conversation_handler = ConversationCallbackHandler()
    stream_handler = AsyncIteratorCallbackHandler()

    # Select chain based on chat_body.mode
    if chat_body.mode == 'rag':
        # RAG-based conversation chain using collection context
        chain = conversation_rag_chain(
            collection=collection,
            chat_params=ChatParams(**chat_body.model_dump()),
            answer_callbacks=[stream_handler] if chat_body.streaming else [],
        )
        embeddings = collection.cmetadata.get('embeddings', None)
    elif chat_body.mode == 'conversation':
        # Test mode - currently same as simple conversation
        chain = conversation_chain(
            chat_params=ChatParams(**chat_body.model_dump()),
            answer_callbacks=[stream_handler] if chat_body.streaming else [],
        )
        embeddings = None

    with token_usage_callback() as token_callback:
        if not chat_body.streaming or test_models_in_use():
            return await run_chain(
                chain=chain,
                chat_body=chat_body,
                lang=lang,
                token_callback=token_callback,
                x_chat_session=x_chat_session,
                embeddings=embeddings,
                chain_callbacks=[conversation_handler],
            )

        asyncio.create_task(run_chain(
            chain=chain,
            chat_body=chat_body,
            lang=lang,
            token_callback=token_callback,
            x_chat_session=x_chat_session,
            embeddings=embeddings,
            chain_callbacks=[conversation_handler],
        ))

        async def event_generator(
            stream_callback: AsyncIteratorCallbackHandler,
            conversation_callback: ConversationCallbackHandler,
            token_callback: TokensCallbackHandler,
            chat_body: ChatBody,
            x_chat_session: str | None = None,
        ):
            ait = stream_callback.aiter()

            async for token in ait:
                yield token

            await conversation_callback.wait_conversation_done()

            yield conversation_callback.chain_result(
                callb=token_callback,
                question=chat_body.question,
                collection=chat_body.collection,
                x_chat_session=x_chat_session,
            )

        return StreamingResponse(event_generator(
            stream_callback=stream_handler,
            conversation_callback=conversation_handler,
            token_callback=token_callback,
            chat_body=chat_body,
            x_chat_session=x_chat_session,
        ))


def chat_language(chat_body: ChatBody, cmetadata: dict) -> str:
    """Retrieve the language to be used in Q/A response"""
    chat_lang = chat_body.chat_lang or cmetadata.get('chat_lang')

    return chat_lang if chat_lang else ''


def retrieve_chat_history(history: list, question: str,
                          session: str = None, embeddings: dict | None = None) -> list:
    """Retrieve chat history to be used in final prompt creation"""
    chat_hist = chat_history.history(
        chat_history=history,
        session=session,
    )
    if chat_hist and not chat_history.is_related(chat_hist, question, embeddings):
        chat_hist = []

    return chat_hist


async def run_chain(
    chain: Chain,
    chat_body: ChatBody,
    lang: str,
    token_callback: TokensCallbackHandler,
    x_chat_session: str,
    embeddings: dict | None = None,
    chain_callbacks: list[BaseCallbackHandler] | None = None,
):
    """Run chain usign async methods and return result"""
    result = await chain.ainvoke({
        'question': chat_body.question,
        'chat_history': retrieve_chat_history(
            history=chat_body.chat_history,
            question=chat_body.question,
            session=x_chat_session,
            embeddings=embeddings,
        ),
        'lang': lang,
    },
        config={'callbacks': chain_callbacks},
        return_only_outputs=True,
    )
    return chat_result(
        result=result,
        callb=token_callback,
        chat_body=chat_body,
        x_chat_session=x_chat_session
    )


def chat_result(
    result: dict | AIMessage,
    callb: TokensCallbackHandler,
    chat_body: ChatBody,
    x_chat_session: str | None = None,
) -> dict:
    """ Handle chat result: save chat history and return answer """
    answer = glom(result, 'answer', default=glom(result, 'content', default=''))
    answer = str(answer).strip(" \n")

    chat_history_id = None
    if not chat_body.streaming:
        chat_hist = chat_history.add_history(
            session_id=x_chat_session,
            collection=chat_body.collection,
            question=chat_body.question,
            answer=answer,
            metadata=token_usage(callb),
        )
        chat_history_id = None if chat_hist is None else str(chat_hist.uuid)

    context = result['context'] if 'context' in result else None

    return {
        'bot': answer,
        'docs': None if not chat_body.source_docs else context,
        'chat_history_id': chat_history_id,
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
