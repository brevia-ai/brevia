"""Question-answering and search functions against a vector database."""
from os import path
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chains.base import Chain
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.llm import LLMChain
from langchain.prompts import load_prompt
from langchain.prompts import (
    ChatPromptTemplate,
)
from langchain.prompts.loading import load_prompt_from_config
from pydantic import BaseModel
from brevia.connection import connection_string
from brevia.collections import single_collection_by_name
from brevia.callback import AsyncLoggingCallbackHandler
from brevia.models import load_chatmodel, load_embeddings
from brevia.settings import get_settings

# system = load_prompt(f'{prompts_path}/qa/default.system.yaml')
# jinja2 template from file was disabled by langchain so, for now
# we load from here
DEFAULT_TEMPLATE = """

                """


def load_condense_prompt(prompts: dict | None) -> ChatPromptTemplate:
    """
        Check if specific few-shot prompt file exists for the collection, if not,
        check for condense prompt file, otherwise, load default condense prompt file.
    """
    if prompts:
        if prompts.get('few'):
            return load_prompt_from_config(prompts.get('few'))
        if prompts.get('condense'):
            return load_prompt_from_config(prompts.get('condense'))

    prompts_path = f'{path.dirname(__file__)}/prompts'

    return load_prompt(f'{prompts_path}/qa/default.condense.yaml')


class SearchQuery(BaseModel):
    """ Search query items """
    query: str
    collection: str
    docs_num: int | None = None
    distance_strategy_name: str = 'cosine',
    filter: dict[str, str | dict] | None = None


class CompletionParams(BaseModel):
    """ Q&A basic conversation chain params"""
    streaming: bool = False


def simple_completion_chain(
    completion_params: CompletionParams,
    answer_callbacks: list[BaseCallbackHandler] | None = None,
    conversation_callbacks: list[BaseCallbackHandler] | None = None,
) -> Chain:
    """
        Return simple completion chain for a generit Input text

        completion_params:

        answer_callbacks: callbacks to use in the final LLM answer to enable streaming
            (default empty list)
        conversation_callbacks: callback to handle conversation results
            (default empty list)
    """

    settings = get_settings()
    if answer_callbacks is None:
        answer_callbacks = []
    if conversation_callbacks is None:
        conversation_callbacks = []


    prompts = completion_params.prompt

    qa_llm_conf = collection.cmetadata.get(
        'qa_completion_llm',
        settings.qa_completion_llm.copy()
    )

    verbose = settings.verbose_mode

    logging_handler = AsyncLoggingCallbackHandler()

    # Create chain for follow-up question using chat history (if present)
    question_generator = LLMChain(
        llm=fup_llm,
        prompt=load_condense_prompt(prompts),
        verbose=verbose,
        callbacks=[logging_handler],
    )

    # Model to use in final prompt
    answer_callbacks.append(logging_handler)
    qa_llm_conf['callbacks'] = answer_callbacks
    qa_llm_conf['streaming'] = chat_params.streaming

    chatllm = load_chatmodel(qa_llm_conf)

    # this chain use "stuff" to elaborate context
    doc_chain = load_qa_chain(
        llm=chatllm,
        prompt=load_qa_prompt(prompts),
        chain_type="stuff",
        verbose=verbose,
        callbacks=[logging_handler],
    )

    # main chain, do all the jobs
    search_kwargs = {'k': chat_params.docs_num, 'filter': chat_params.filter}

    conversation_callbacks.append(logging_handler)
    return ConversationalRetrievalChain(

        combine_docs_chain=doc_chain,

        question_generator=question_generator,
        callbacks=conversation_callbacks,
        verbose=verbose,
    )
