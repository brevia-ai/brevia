"""Functions to perform summarization & document analysis"""
from langchain.docstore.document import Document
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import TokenTextSplitter
from langchain.chat_models.base import BaseChatModel
from langchain.prompts.loading import load_prompt_from_config
from brevia.callback import LoggingCallbackHandler
from brevia.models import load_chatmodel
from brevia.settings import get_settings


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

    The 'refine' summarization chain breaks the document into chunks pieces, then
    concentrates on making the summary better by refining it.
    Starts using the initial prompt for the first chunk then uses the iteration prompt
    over the remaining chunks to further enhance the summary.

    Args:
        prompts (dict | None): Optional prompts for customization.
        It should be a dictionary with the following keys:
        - 'initial_prompt' (dict): The prompt to use for the first chunk summarization.
        - 'iteration_prompt' (dict | None): (Optional) The prompt to use for increase
        information over the chunk pieces.

    Returns:
        dict: Custom prompts for 'refine' summarization chain.
    """

    prompts_data = {}
    if prompts.get('initial_prompt'):
        question_prompt = load_prompt_from_config(prompts.get('initial_prompt'))
        prompts_data['question_prompt'] = question_prompt
        if prompts.get('iteration_prompt'):
            refine_prompt = load_prompt_from_config(prompts.get('iteration_prompt'))
            prompts_data['refine_prompt'] = refine_prompt

    return prompts_data


def get_summarize_llm() -> BaseChatModel:
    """Get a summarization language model for text summarization.

    This function returns a language model for use in the summarization process.
    The model's configuration is defined by environment variables.

    Returns:
        BaseChatModel: A language model suitable for text summarization.

    """
    model = get_settings().summarize_llm.copy()
    model['callbacks'] = [LoggingCallbackHandler()]

    return load_chatmodel(model)


def summarize(
    text: str,
    chain_type: str | None = None,
    initial_prompt: dict | None = None,
    iteration_prompt: dict | None = None
) -> str:
    """Perform summarizing for a given text.
    This function takes a text as input and generates a summary using
    langchain summarization chain main alghoritms (stuff, map_reduce, refine).

    Args:
        text: The input text that you want to summarize.
        chain_type: The main langchain summarization chain type should be one of
            "stuff", "map_reduce", and "refine".
            if not providerd stuff is used by default
        initial_prompt: Optional custom prompt to be used in the selected langchain
            chain type to replace the main chain prompt defaults.
        iteration_prompt: Optional custom prompts to be used in the selected
            langchain chain type to replace the second chain promopt defaults.

    Returns:
        str: The generated summary of the input text.

    Raises:
        ValueError: If an unsupported summarization chain type is specified.
    """

    summarize_chain_map = {
        'stuff': load_stuff_prompts,
        'map_reduce': load_map_prompts,
        'refine': load_refine_prompts
    }
    settings = get_settings()
    chain_type = chain_type or settings.summ_default_chain
    if chain_type not in summarize_chain_map:
        raise ValueError(
            f"Got unsupported chain type: {chain_type}. "
            f"Should be one of {list(summarize_chain_map.keys())}"
        )

    logging_handler = LoggingCallbackHandler()
    kwargs = {
        'llm': get_summarize_llm(),
        'chain_type': chain_type,
        'verbose': settings.verbose_mode,
        'callbacks': [logging_handler],
    }

    # load chain_type specific prompts:
    prompts_args = summarize_chain_map[chain_type]({
        'initial_prompt': initial_prompt,
        'iteration_prompt': iteration_prompt
    })

    chain = load_summarize_chain(**kwargs, **prompts_args)
    text_splitter = TokenTextSplitter(
        chunk_size=settings.summ_token_splitter,
        chunk_overlap=settings.summ_token_overlap
    )
    texts = text_splitter.split_text(text)
    docs = [Document(page_content=t) for t in texts]

    return chain.run(**{'input_documents': docs})
