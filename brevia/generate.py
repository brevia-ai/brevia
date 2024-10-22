"""Function to generate questions over a document"""
from os import environ, path
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.loading import load_prompt, load_prompt_from_config
from langchain.chains.summarize import load_summarize_chain
from langchain.docstore.document import Document
from langchain.text_splitter import TextSplitter, NLTKTextSplitter
from brevia import load_file
from brevia.callback import LoggingCallbackHandler
from brevia.models import load_chatmodel


def load_generations_prompts(prompts: dict) -> dict[str, type[BasePromptTemplate]]:
    """Load analysis prompts"""
    return {
        'generate_questions_prompt': load_single_prompt(
            prompts, 'questions_generation'
        ),
        'refine_prompt': load_single_prompt(
            prompts, 'questions_generation_refine'
        ),
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
        chunk_size=int(6000),
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

    text = load_file.read(file_path=file_path, **LOAD_PDF_OPTIONS)
    pages = load_splitter().split_documents([Document(page_content=text)])

    output = run_chain_questions(pages, prompts)
    print(output)
    generated_q = output.pop('output_text')
    # raw_data = output.pop('input')
    text_output = f'{generated_q}\n\n\n'

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

    kwargs = {
        'llm': llm_text,
        'chain_type': "refine",
        'verbose': True,
        'callbacks': [logging_handler],
    }
    # Using summarize refine algorithm with modified prompts
    # for informations extraction on multiple pages
    chain = load_summarize_chain(
        **kwargs,
        question_prompt=prompts.get('generate_questions_prompt'),
        refine_prompt=prompts.get('refine_prompt'),
    )

    return chain.invoke({'input_documents': pages}, return_only_outputs=True)
