"""Completion API endpoints"""
from langchain.chains.base import Chain
from fastapi import APIRouter
from brevia.dependencies import (
    get_dependencies,
)
from brevia.completions import CompletionParams, simple_completion_chain
from brevia.callback import token_usage_callback, token_usage, TokensCallbackHandler

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
    with token_usage_callback() as callb:
        result = await chain.ainvoke({
            'text': completion_body.text
        }, return_only_outputs=True)
    return completion_result(
        result=result,
        callb=callb,
    )


def completion_result(
    result: dict,
    callb: TokensCallbackHandler,
) -> dict:
    """ Handle chat result: save chat history and return answer """
    answer = result['text'].strip(" \n")

    return {
        'completion': answer,
        'usage': token_usage(callb),
    }
