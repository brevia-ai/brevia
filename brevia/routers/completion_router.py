"""API endpoints for question answering and search"""
from langchain.callbacks import get_openai_callback
from langchain_community.callbacks.openai_info import OpenAICallbackHandler
from langchain.chains.base import Chain
from fastapi import APIRouter, Header
from brevia.dependencies import (
    get_dependencies,
)
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
):
    """ /completion endpoint, send a text with a custom prompt and get a completion """

    chain = simple_completion_chain(
        completion_params=CompletionParams(**completion_body.model_dump()),
    )

    return await run_chain(
        chain=chain,
        completion_body=completion_body,
    )


async def run_chain(
    chain: Chain,
    completion_body: CompletionBody,
):
    """Run chain usign async methods and return result"""
    with get_openai_callback() as callb:
        result = await chain.acall({
            'text': completion_body.text
        })
    return completion_result(
        result=result,
        completion_body=completion_body,
        callb=callb,
    )


def completion_result(
    result: dict,
    completion_body: CompletionBody,
    callb: OpenAICallbackHandler,
) -> dict:
    """ Handle chat result: save chat history and return answer """
    answer = result['text'].strip(" \n")

    print(callb)
    return {
        'completion': answer
    }
