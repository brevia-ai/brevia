"""API endpoints for question answering and search"""
from typing import Annotated
import asyncio
from langchain.callbacks import AsyncIteratorCallbackHandler, get_openai_callback
from langchain.callbacks.openai_info import OpenAICallbackHandler
from langchain.chains.base import Chain
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from brevia.dependencies import (
    get_dependencies,
)
from brevia.callback import ConversationCallbackHandler
from brevia.completions import CompletionParams, simple_completion_chain
from brevia.models import test_models_in_use

router = APIRouter()

class CompletionBody(CompletionParams):
    """ /completion request body """
    text: str
    prompt: dict | None = None
    token_data: bool = False

@router.post('/completion', dependencies=get_dependencies())
async def completion_action(
    completion_body: CompletionBody,
    x_chat_session: Annotated[str | None, Header()] = None,
):
    """ /completion endpoint, send a text with a custom prompt and get a completion """
    conversation_handler = ConversationCallbackHandler()
    stream_handler = AsyncIteratorCallbackHandler()
    chain = simple_completion_chain(
        completion_params=CompletionParams(**completion_body.model_dump()),
        answer_callbacks=[stream_handler] if completion_body.streaming else [],
        conversation_callbacks=[conversation_handler]
    )

    if not completion_body.streaming or test_models_in_use():
        return await run_chain(
            chain=chain,
            completion_body=completion_body,
            x_chat_session=x_chat_session,
        )

    asyncio.create_task(run_chain(
        chain=chain,
        completion_body=completion_body,
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
    ))


async def run_chain(
    chain: Chain,
    completion_body: CompletionBody,
    x_chat_session: str,
):
    """Run chain usign async methods and return result"""
    with get_openai_callback() as callb:
        result = await chain.acall({
            'text': completion_body.text,
            'prompt': completion_body.prompt
        })

    return completion_result(
        result=result,
        completion_body=completion_body,
        callb=callb
    )


def completion_result(
    result: dict,
    completion_body: CompletionBody,
    callb: OpenAICallbackHandler,
) -> dict:
    """ Handle chat result: save chat history and return answer """
    answer = result['answer'].strip(" \n")

    return {
        'bot': answer,
        'token_data': None if not completion_body.token_data else callb.__dict__
    }

