"""Simple completion functions"""
from langchain.chains.base import Chain
from langchain.chains.llm import LLMChain
from langchain_core.prompts.loading import load_prompt_from_config
from pydantic import BaseModel
from brevia.models import load_chatmodel
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

    # Check if completion_llm config is provided in completion_params
    if (completion_params.config
            and completion_params.config.get('completion_llm')):
        llm_conf = completion_params.config['completion_llm'].copy()
    else:
        llm_conf = settings.qa_completion_llm.copy()
    comp_llm = load_chatmodel(llm_conf)
    completion_llm = LLMChain(
        llm=comp_llm,
        prompt=load_custom_prompt(completion_params.prompt),
        verbose=verbose,
    )

    return completion_llm
