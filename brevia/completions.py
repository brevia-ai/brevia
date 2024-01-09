"""Question-answering and search functions against a vector database."""
from langchain.chains.base import Chain
from langchain.chains.llm import LLMChain
from langchain.prompts import load_prompt
from langchain.prompts import (
    ChatPromptTemplate,
)
from langchain.prompts.loading import load_prompt_from_config
from pydantic import BaseModel
from brevia.callback import AsyncLoggingCallbackHandler
from brevia.models import load_chatmodel
from brevia.settings import get_settings

# system = load_prompt(f'{prompts_path}/qa/default.system.yaml')
# jinja2 template from file was disabled by langchain so, for now
# we load from here
DEFAULT_TEMPLATE = """
                """


class CompletionParams(BaseModel):
    """ Q&A basic conversation chain params"""
    streaming: bool = False


def simple_completion_chain(
    completion_params: CompletionParams,
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
    llm_conf = settings.qa_completion_llm
    comp_llm = load_chatmodel(llm_conf)
    verbose = settings.verbose_mode
    logging_handler = AsyncLoggingCallbackHandler()

    # Create chain for follow-up question using chat history (if present)
    completion_llm = LLMChain(
        llm=comp_llm,
        prompt=load_prompt(completion_params.prompt),
        verbose=verbose,
        callbacks=[logging_handler],
    )

    return completion_llm
