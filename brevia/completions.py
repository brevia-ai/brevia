"""Simple completion functions"""
from langchain.chains.base import Chain
from langchain.chains.llm import LLMChain
from langchain_core.prompts.loading import load_prompt_from_config
from pydantic import BaseModel
from brevia.models import load_chatmodel, get_model_config
from brevia.settings import get_settings


class CompletionParams(BaseModel):
    """ Q&A basic conversation chain params """
    prompt: dict | None = None
    config: dict | None = None


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
    verbose = settings.verbose_mode

    llm_conf = get_model_config(
        'qa_completion_llm',
        user_config=completion_params.config,
        default=settings.qa_completion_llm.copy()
    )
    comp_llm = load_chatmodel(llm_conf)
    completion_llm = LLMChain(
        llm=comp_llm,
        prompt=load_custom_prompt(completion_params.prompt),
        verbose=verbose,
    )

    return completion_llm
