"""Base class for text analysis services"""
from langchain.docstore.document import Document
from langchain_core.callbacks import Callbacks
from langchain.chains.combine_documents.refine import RefineDocumentsChain
from langchain.chains.llm import LLMChain
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts.loading import load_prompt_from_config
from brevia.callback import LoggingCallbackHandler
from brevia.load_file import read
from brevia.index import split_document
from brevia.models import load_chatmodel
from brevia.prompts import load_prompt_from_yaml
from brevia.settings import get_settings
from brevia.tasks.base import BaseAnalysisTask


class BaseTextAnalysisTask(BaseAnalysisTask):
    """Base class for text analysis tasks"""

    def text_documents(
            self,
            file_path: str,
            options: dict | None = None
    ) -> list[Document]:
        """Load text from file and split into documents"""
        text = read(file_path=file_path)
        options = options or {}

        return split_document(Document(page_content=text), collection_meta=options)


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
                self.file_path, options=self.text_options)

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
        llm_conf = self.llm_conf or get_settings().summarize_llm.copy()
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
