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


def load_stuff_prompts(prompts: dict | None) -> dict:
    """Load custom prompts for the 'stuff' summarization chain.
    Summarization chain is the simplest one and have only one prompt

    Args:
        prompts (dict | None): Optional prompts for customization.
        It should be a dictionary with the following keys:
        - 'initial_prompt' (dict): The prompt to use for the initial summarization.

    Returns:
        dict: Custom prompts for 'stuff' summarization chain.
    """
    if prompts.get('initial_prompt'):
        return {
            'prompt': load_prompt_from_config(prompts.get('initial_prompt'))
        }

    return {}


def load_map_prompts(prompts: dict | None) -> dict:
    """Load custom prompts for the 'map_reduce' summarization chain.
    The 'map_reduce' summarization chain utilizes a more sophisticated algorithm that
    merges multiple prompts to create a summary. It divides the text into text chunks
    and applies the initial prompt to each of them. Afterward, it uses the iteration
    prompt to combine all the result into a final summary.

    Args:
        prompts (dict | None): Optional prompts for customization.
        It should be a dictionary with the following keys:
        - 'initial_prompt' (dict): The prompt to use for the chunks summarization.
        - 'iteration_prompt' (dict | None): (Optional) The prompt to use for summarizing
            all the pieces.

    Returns:
        dict: Custom prompts for 'map_reduce' summarization chain.
    """
    prompts_data = {}
    if prompts.get('initial_prompt'):
        map_prompt = load_prompt_from_config(prompts.get('initial_prompt'))
        prompts_data['map_prompt'] = map_prompt
        prompts_data['combine_prompt'] = map_prompt
        if prompts.get('iteration_prompt'):
            combine_prompt = load_prompt_from_config(prompts.get('iteration_prompt'))
            prompts_data['combine_prompt'] = combine_prompt

    return prompts_data


def load_refine_prompts(prompts: dict | None) -> dict:
    """Load custom prompts for the 'refine' summarization chain.

    The 'refine' summarization chain breaks the document into chunk pieces, then
    concentrates on making the summary better by refining it.
    It starts using the initial prompt for the first chunk and then uses the
    iteration prompt over the remaining chunks to further enhance the summary.

    In LangChain, the default prompt names for the refine algorithm are:
    - question_prompt: The prompt used for summarizing the first chunk.
    - refine_prompt: The prompt used for refining the summary over the remaining chunks.

    Args:
        prompts (dict | None): Optional prompts for customization.
        It should be a dictionary with the following keys:
        - 'initial_prompt' (dict): The prompt to use for the first chunk summarization.
        - 'iteration_prompt' (dict | None): (Optional) The prompt to use for increasing
          information over the chunk pieces.

    Returns:
        dict: Custom prompts for the 'refine' summarization chain.
    """

    prompts_data = {}
    if prompts.get('initial_prompt'):
        question_prompt = load_prompt_from_config(prompts.get('initial_prompt'))
        prompts_data['question_prompt'] = question_prompt
        if prompts.get('iteration_prompt'):
            refine_prompt = load_prompt_from_config(prompts.get('iteration_prompt'))
            prompts_data['refine_prompt'] = refine_prompt

    return prompts_data
