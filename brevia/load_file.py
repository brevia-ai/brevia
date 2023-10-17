"""Read text from a file with different formats"""
import os
import re
import mimetypes
from typing import List, Any
from langchain.docstore.document import Document
from langchain.document_loaders import PyPDFLoader, UnstructuredPDFLoader


def cleanup_text(text_in: str) -> str:
    """ Cleanup input text from multple spaces and newlines"""
    new_text = re.sub(r'\n\n+', '\n\n', text_in)
    new_text = new_text.replace("\x00", " ")
    new_text = re.sub(r'\.\.\.+', '...', new_text)

    return " ".join(new_text.strip().split(' '))


def read_pdf_file(
    file_path: str,
    page_from: int = None,  # from page, used in PDF
    page_to: int = None,  # to page, used in PDF
    **loader_kwargs: Any,
) -> str:
    """
    Load PDF file and return its textual content
    """
    docs = load_documents_pdf(file_path=file_path, **loader_kwargs)
    if page_from is not None:
        docs = [x for x in docs if x.metadata['page'] >= (page_from - 1)]
    if page_to is not None:
        docs = [x for x in docs if x.metadata['page'] <= (page_to - 1)]

    return ' '.join([cleanup_text(item.page_content) for item in docs]).strip()


def load_documents_pdf(file_path: str, **kwargs: Any) -> List[Document]:
    """
    Load documents from PDF file, first try to extract text with PyPDF,
    then use Unstructured and OCR to read
    """
    loader = PyPDFLoader(file_path=file_path)
    docs = loader.load()

    # check if `ocr` argument is passed and not falsy
    if 'ocr' not in kwargs or not kwargs['ocr']:
        return docs

    # try with OCR if extracted text is too short - optional 'min_text_len' parameter
    min_text_len = kwargs['min_text_len'] if 'min_text_len' in kwargs else 100
    text = ' '.join([cleanup_text(item.page_content) for item in docs]).strip()
    if len(text) > min_text_len:
        return docs

    ocr_languages = kwargs['ocr_languages'] if 'ocr_languages' in kwargs else None
    loader = UnstructuredPDFLoader(
        file_path=file_path, mode='elements', strategy='ocr_only',
        ocr_languages=ocr_languages,
    )

    return loader.load()


def read_txt_file(
    file_path: str,
) -> str:
    """
    Load TXT file and return its content
    """
    with open(file_path, 'r') as file:
        text = file.read()

    return cleanup_text(text).strip()


def read(
    file_path: str,
    **loader_kwargs: Any,
) -> str:
    """
    Load text from a txt o pdf file (for now, more formats to come...)
    """

    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    mtype = mimetypes.guess_type(file_path)[0]
    if mtype not in ['application/pdf', 'text/plain']:
        raise ValueError(f'Unsupported file content type "{mtype}"')

    if mtype == 'application/pdf':
        return read_pdf_file(file_path=file_path, **loader_kwargs)

    return read_txt_file(file_path=file_path)
