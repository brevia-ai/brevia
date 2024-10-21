
"""Functions to perform summarization & document analysis"""
import mimetypes
import zipfile
import tempfile
import shutil
import logging
import boto3
from os import environ, path, walk, unlink
from langchain.prompts.loading import load_prompt, load_prompt_from_config
from langchain.chains.llm import LLMChain
from langchain.chains.summarize import load_summarize_chain
from langchain.chains import SequentialChain
from langchain.docstore.document import Document
from langchain.schema import BasePromptTemplate
from langchain.text_splitter import TextSplitter, NLTKTextSplitter
from brevia import load_file
from brevia.callback import LoggingCallbackHandler
from brevia.models import load_chatmodel
from typing import List, Optional
from langchain.chains import create_structured_output_runnable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts.loading import load_prompt_from_config
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain_text_splitters import TokenTextSplitter
from brevia.callback import LoggingCallbackHandler
from brevia.models import load_chatmodel
from brevia.settings import get_settings


def load_generations_prompts(prompts: dict) -> dict[str, type[BasePromptTemplate]]:
    """Load analysis prompts"""
    return {
        'generate_questions_prompt': load_single_prompt(prompts, 'questions_generation'),
        'refine_prompt': load_single_prompt(prompts, 'questions_generation_refine'),
    }


def load_single_prompt(prompts: dict, name: str) -> BasePromptTemplate:
    """Load single prompt from dict or file"""
    if name in prompts:
        return load_prompt_from_config(prompts.get(name))

    prompts_path = f'{path.dirname(__file__)}/prompts/generation'

    return load_prompt(f'{prompts_path}/{name}.yaml')


def load_splitter() -> TextSplitter:
    """Return default splitter"""
    return NLTKTextSplitter(
        separator="\n",
        chunk_size=int(3000),
        chunk_overlap=int(500)
    )


LOAD_PDF_OPTIONS = {
    'ocr': bool(environ.get('GQ_OCR', True)),
    'min_text_len': int(environ.get('GQ_MIN_TEXT_LEN', 150)),
    # 'ocr_languages': ['ita', 'eng'],
    'ocr_languages': str(environ.get('GQ_OCR_LANGUAGES', 'ita')),
}


def questions(file_path: str, prompts: dict) -> dict:
    """Analysis task"""
    # if is_zip_file(file_path):
    #     pages = load_zip_content(file_path)
    # else:
    text = load_file.read(file_path=file_path, **LOAD_PDF_OPTIONS)
    pages = load_splitter().split_documents([Document(page_content=text)])

    output = run_chain_questions(pages, prompts)
    generated_q = output.pop('questions')
    raw_data = output.pop('input')
    text_output = f'{generated_q}\n\n\nRAW:\n\n{raw_data}'

    # file_path = create_pdf(
    #     checklist=checklist_cod,
    #     summary=raw_data,
    #     title=report_title
    # )
    # file_url = upload_file(file_path=file_path)
    # Remove temporary file
    # unlink(file_path)

    result = {
        'input_documents': [{
            'page_content': doc.page_content,
            'metadata': doc.metadata
        } for doc in pages
        ],
        'output': text_output
        # 'document_url': file_url
    }

    return result


class Question(BaseModel):
    """formatted output"""
    question: str = Field(description="Domanda")
    type: str = Field(description="Tipologia")
    data: str = Field(description="Dati")


def run_chain_questions(pages: list[Document], prompts: dict) -> dict[str, str]:
    """Run anlysis chain"""
    prompts = load_generations_prompts(prompts)
    logging_handler = LoggingCallbackHandler()
    llm_text = load_chatmodel({
        '_type': 'openai-chat',
        'model_name': 'gpt-4o',
        'temperature': 0.0,
        'callbacks': [logging_handler],
    })

    # Using summarize refine algorithm with modified prompts
    # for informations extraction on multiple pages
    data_extraction_chain = load_summarize_chain(
        llm_text,
        chain_type="refine",
        question_prompt=prompts.get(''),
        refine_prompt=prompts.get(''),
        output_key="input",
        # return_intermediate_steps=True,
    )

    checklist_cod_chain = LLMChain(
        llm=llm_text,
        prompt=prompts.get('generate_questions_prompt'),
        output_key="questions",
        callbacks=[logging_handler],
    )

    overall_chain = SequentialChain(
        chains=[
            data_extraction_chain,
            checklist_cod_chain,
        ],
        input_variables=["input_documents"],
        output_variables=[
            "input", "questions"
        ],
        # verbose=True,
    )

    return overall_chain({'input_documents': pages})
