""" Functions to handle prompts."""

from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.loading import (
    load_prompt_from_config,
    _load_few_shot_prompt,
)
import yaml
from brevia.settings import get_settings


def prompt_file_path(relative_path: str):
    """ Get the full path of a prompt file, given the relative path """
    return f'{get_settings().prompts_base_path}/{relative_path}'


def load_prompt_from_yaml(relative_path: str) -> PromptTemplate:
    """ Load a prompt from a yaml file, given the prompt file relative path """
    file_path = prompt_file_path(relative_path)
    with open(file_path) as f:
        config = yaml.safe_load(f)
    if not config:
        raise ValueError(f'Failed to load prompt from {file_path}')
    type = config.pop('_type', 'prompt')
    if type == 'few_shot':
        return _load_few_shot_prompt(config)

    return PromptTemplate(**config)


def load_qa_prompt(prompts: dict | None = None) -> ChatPromptTemplate:
    """
        Load prompt for RAG-Q/A, following system/human/ai pattern.
        If prompts are provided, they will overwrite the default prompts.
        Otherwise, the default prompts will be loaded from the default path:
            - rag/human.yml: human prompt, the user input
            - rag/system.yml: system prompt, base instruction for the model behavior
    """
    human = load_prompt_from_yaml('rag/human.yml')
    system = load_prompt_from_yaml('rag/system.yml')

    if prompts:
        if prompts.get('system'):
            system = load_prompt_from_config(prompts.get('system'))
        if prompts.get('human'):
            human = load_prompt_from_config(prompts.get('human'))

    system_message_prompt = SystemMessagePromptTemplate(prompt=system)
    human_message_prompt = HumanMessagePromptTemplate(prompt=human)

    return ChatPromptTemplate.from_messages(
        [system_message_prompt, human_message_prompt]
    )


def load_condense_prompt(config: dict | None = None) -> BasePromptTemplate:
    """
        Load prompt for RAG-Condense, to create the follow-up question
        in a conversation.
        Prompt config is loaded if provided, otherwise, it will load
        the default 'rag/condense.yml' prompt.
    """
    if config:
        return load_prompt_from_config(config=config)

    return load_prompt_from_yaml('rag/condense.yml')
