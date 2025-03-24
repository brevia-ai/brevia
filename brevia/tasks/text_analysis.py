"""Base class for text analysis services"""
from langchain.docstore.document import Document
from langchain.chains.summarize import load_summarize_chain
from langchain.chains.combine_documents.refine import RefineDocumentsChain
from langchain.chains.llm import LLMChain
from langchain_core.callbacks import Callbacks
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts.loading import load_prompt_from_config
from brevia.callback import LoggingCallbackHandler
from brevia.load_file import read
from brevia.index import split_document
from brevia.models import load_chatmodel
from brevia.prompts import (
    load_prompt_from_yaml,
    load_stuff_prompts,
    load_map_prompts,
    load_refine_prompts
)
from brevia.settings import get_settings
from brevia.tasks.base import BaseAnalysisTask


class BaseTextAnalysisTask(BaseAnalysisTask):
    """Base class for text analysis tasks"""

    def text_documents(
            self,
            input_data: str,
            is_file_path: bool = True,
            options: dict | None = None
    ) -> list[Document]:
        """
        Load text from a file or directly from a string and split into documents.

        Args:
            input_data (str): The file path or the text content.
            is_file_path (bool): Flag to indicate if input_data is a file path
                or text content.
            options (dict | None): Additional options for splitting the document.

        Returns:
            list[Document]: A list of Document objects.
        """
        if is_file_path:
            text = read(file_path=input_data)
        else:
            text = input_data

        options = options or {}
        return split_document(Document(page_content=text), collection_meta=options)


class SummarizeTextAnalysisTask(BaseTextAnalysisTask):
    """Text summarization chain"""

    def __init__(
        self,
        text: str,
        chain_type: str | None = None,
        initial_prompt: dict | None = None,
        iteration_prompt: dict | None = None,
        llm_conf: dict | None = None,
        text_options: dict | None = None,
    ):
        self.text = text
        self.chain_type = chain_type
        self.initial_prompt = initial_prompt
        self.iteration_prompt = iteration_prompt
        self.llm_conf = llm_conf
        self.text_options = text_options
        self.load_analysis_prompts({
            'initial_prompt': self.initial_prompt,
            'iteration_prompt': self.iteration_prompt
        })

    def perform_task(self):
        """Service logic"""

        text_documents = self.text_documents(
            self.text, is_file_path=False, options=self.text_options)

        result = self.run_summarize_chain(text_documents)

        return {
            'input_documents': [{
                'page_content': doc.page_content,
                'metadata': doc.metadata
            } for doc in text_documents
            ],
            'output_text': result.get('output_text')
        }

    def load_analysis_prompts(self, prompts: dict | None = None):
        """Load analysis prompts"""
        if not prompts:
            raise ValueError('Prompts dictionary must be provided.')

        summarize_chain_map = {
            'stuff': load_stuff_prompts,
            'map_reduce': load_map_prompts,
            'refine': load_refine_prompts
        }

        chain_type = self.chain_type or get_settings().summ_default_chain
        if chain_type not in summarize_chain_map:
            raise ValueError(
                f"Got unsupported chain type: {chain_type}. "
                f"Should be one of {list(summarize_chain_map.keys())}"
            )

        missing = {'initial_prompt'} - prompts.keys()
        if missing:
            raise ValueError(f'Missing required prompts: {", ".join(missing)}')

        # load chain_type specific prompts:
        self.prompts = summarize_chain_map[chain_type](prompts)
        self.chain_type = chain_type

    def run_summarize_chain(
        self,
        pages: list[Document],
    ) -> dict[str, str]:
        """Run summarization chain"""

        logging_handler = LoggingCallbackHandler()
        llm_conf = self.llm_conf or get_settings().summarize_llm.copy() \
            # pylint: disable=no-member
        llm_conf['callbacks'] = [logging_handler]
        llm_text = load_chatmodel(llm_conf)

        kwargs = {
            'llm': llm_text,
            'chain_type': self.chain_type,
            'verbose': get_settings().verbose_mode,
            'callbacks': [logging_handler],
        }

        chain = load_summarize_chain(**kwargs, **self.prompts)
        return chain.invoke({'input_documents': pages}, return_only_outputs=True)


class RefineTextAnalysisTask(BaseTextAnalysisTask):
    """Text analysis using refine chain"""

    def __init__(
        self,
        file_path: str,
        prompts: dict | None = None,
        llm_conf: dict | None = None,
        text_options: dict | None = None,
    ):
        self.file_path = file_path
        self.llm_conf = llm_conf
        self.text_options = text_options
        self.load_analysis_prompts(prompts)

    def perform_task(self):
        """Service logic"""
        text_documents = self.text_documents(
            self.file_path, is_file_path=True, options=self.text_options)

        result = self.run_refine_chain(text_documents)

        return {
            'input_documents': [{
                'page_content': doc.page_content,
                'metadata': doc.metadata
            } for doc in text_documents
            ],
            'output_text': result.get('output_text')
        }

    def load_analysis_prompts(self, prompts: dict | None = None):
        """Load analysis prompts"""
        if not prompts:
            raise ValueError('Prompts dictionary must be provided.')
        missing = {'initial_prompt', 'refine_prompt'} - prompts.keys()
        if missing:
            raise ValueError(f'Missing required prompts: {", ".join(missing)}')

        for key, value in prompts.items():
            if isinstance(value, dict):
                prompts[key] = load_prompt_from_config(value)
            else:
                prompts[key] = load_prompt_from_yaml(value)

        self.prompts = prompts

    def run_refine_chain(
        self,
        pages: list[Document],
    ) -> dict[str, str]:
        """Run analysis with refine chain"""
        logging_handler = LoggingCallbackHandler()
        llm_conf = self.llm_conf or get_settings().summarize_llm.copy()  \
            # pylint: disable=no-member
        llm_conf['callbacks'] = [logging_handler]
        llm_text = load_chatmodel(llm_conf)

        # Using refine algorithm with modified prompts
        # for informations extraction on multiple pages
        chain = self.load_refine_chain(
            llm=llm_text,
            callbacks=[logging_handler],
        )

        return chain.invoke({'input_documents': pages}, return_only_outputs=True)

    def load_refine_chain(
        self,
        llm: BaseLanguageModel,
        callbacks: Callbacks,
        verbose: bool = True,
    ) -> RefineDocumentsChain:
        """Load refine chain"""
        initial_prompt = self.prompts.get('initial_prompt')
        refine_prompt = self.prompts.get('refine_prompt')

        return RefineDocumentsChain(
            initial_llm_chain=LLMChain(llm=llm, prompt=initial_prompt, verbose=verbose),
            refine_llm_chain=LLMChain(llm=llm, prompt=refine_prompt, verbose=verbose),
            document_variable_name='text',
            initial_response_name='existing_answer',
            verbose=verbose,
            callbacks=callbacks,
        )
