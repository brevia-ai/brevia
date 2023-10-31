"""Returning analysis chain against a text prvided"""
from os import environ, path
from langchain.docstore.document import Document
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import TokenTextSplitter
from langchain.chat_models.base import BaseChatModel
from langchain.prompts import load_prompt
from langchain.prompts import (
    ChatPromptTemplate,
)
from langchain.prompts.loading import load_prompt_from_config
from brevia.callback import LoggingCallbackHandler
from brevia.models import load_chatmodel

PROMPT_SAMPLES_TYPE = {
    'custom',
    'summarize',
    'summarize_point',
    'classification',
}

SUMMARIZE_CHAIN_TYPE = {
    'stuff': 'prompt',
    'map_reduce': 'map_prompt',
    'refine': 'question_prompt',
}


def load_summarize_prompt(prompt: dict | None) -> ChatPromptTemplate:
    """Load a summarization prompt.
    This function loads a summarization prompt based on the provided dictionary
    or uses a default prompt if none is specified.
    default prompt are:
    - summarize
    - summarize_point
    - classification

    Args:
        prompt: A dictionary specifying a custom summarization prompt.
            If not provided, local 'default.summarize' prompt will be used.

    Returns:
        ChatPromptTemplate: A chat prompt template that can be used for summarization.
    """
    prompts_path = f'{path.dirname(__file__)}/prompts'

    if prompt:
        for value in prompt.items():
            if value not in PROMPT_SAMPLES_TYPE:
                raise ValueError(f"Invalid value '{value}' in the custom prompts."
                                 f"Values must be one of {PROMPT_SAMPLES_TYPE}.")

        if prompt.get('custom'):
            return load_prompt_from_config(prompt.get('custom'))

        return load_prompt(f'{prompts_path}/analysis/yaml/default.{prompt}.yaml')

    return load_prompt(f'{prompts_path}/analysis/yaml/default.summarize.yaml')


def get_summarize_llm() -> BaseChatModel:
    """Get a summarization language model for text summarization.

    This function returns a language model for use in the summarization process.
    The model's configuration is defined by environment variables.

    Returns:
        BaseChatModel: A language model suitable for text summarization.

    """
    logging_handler = LoggingCallbackHandler()

    return load_chatmodel({
        '_type': 'openai-chat',
        'model_name': environ.get('SUMM_COMPLETIONS_MODEL'),
        'temperature': float(environ.get('SUMM_TEMPERATURE', 0)),
        'max_tokens': int(environ.get('SUMM_MAX_TOKENS', 2000)),
        'callbacks': [logging_handler],
    })


def summarize(
    text: str,
    summ_type: str | None,
    prompt: str | None,
    num_items: int | None
) -> str:
    """Perform summarizing for a given text.

    This function takes a text as input and generates a summary using
    a specified langchain summarization chain main method (stuff, map_reduce, refine).
    It also supports basic prompts customization with local yaml files

    Args:
        text: The input text that you want to summarize.
        summ_type: The main langchain summarization chain type Should be one of "stuff",
            "map_reduce", and "refine". if not providerd map_reduce is used by default
        prompt: Prompt to be used in the chain.
            From default files or inside 'custom' field.
        num_items: The number of summary items for summarization_point
            and classification custom prompt.

    Returns:
        str: The generated summary of the input text.

    Raises:
        ValueError: If an unsupported summarization chain type is specified.
    """
    if num_items is None:
        num_items = int(environ.get('SUMM_NUM_ITEMS', 5))

    summ_type = summ_type or environ.get('SUMM_DEFAULT_TYPE', "map_reduce")
    if summ_type not in SUMMARIZE_CHAIN_TYPE:
        raise ValueError(
            f"Got unsupported chain type: {summ_type}. "
            f"Should be one of {SUMMARIZE_CHAIN_TYPE.keys()}"
        )

    logging_handler = LoggingCallbackHandler()
    kwargs = {
        'llm': get_summarize_llm(),
        'chain_type': summ_type,
        'verbose': environ.get('VERBOSE_MODE', False),
        SUMMARIZE_CHAIN_TYPE[summ_type]: load_summarize_prompt(prompt),
        'callbacks': [logging_handler],
    }
    chain = load_summarize_chain(**kwargs)

    text_splitter = TokenTextSplitter(
        chunk_size=int(environ.get("SUMM_TOKEN_SPLITTER", 4000)),
        chunk_overlap=int(environ.get("SUMM_TOKEN_OVERLAP", 500))
    )
    texts = text_splitter.split_text(text)
    docs = [Document(page_content=t) for t in texts]

    return chain.run(**{'input_documents': docs, 'num_items': num_items})
