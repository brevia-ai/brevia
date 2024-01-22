"""Simple completion functions"""
from langchain.chains.base import Chain
from langchain.chains.llm import LLMChain
from langchain.prompts.loading import load_prompt_from_config
from pydantic import BaseModel
from brevia.models import load_chatmodel
from brevia.settings import get_settings


class CompletionParams(BaseModel):
    """ Q&A basic conversation chain params """
    prompt: dict | None = None


def load_custom_prompt(prompt: dict | None):
    """ Load custom prompt """
    return load_prompt_from_config(prompt)


def simple_completion_chain(
    completion_params: CompletionParams,
) -> Chain:
    """
        Return simple completion chain for a generic input text

        completion_params: basic completion params including:
            prompt: custom prompt for execute simple completion commands
    """

    settings = get_settings()
    llm_conf = settings.qa_completion_llm.copy()
    comp_llm = load_chatmodel(llm_conf)
    verbose = settings.verbose_mode
    # Create chain for follow-up question using chat history (if present)
    completion_llm = LLMChain(
        llm=comp_llm,
        prompt=load_custom_prompt(completion_params.prompt),
        verbose=verbose,
    )

    return completion_llm
