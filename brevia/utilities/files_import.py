"""Utility functions to import files or folders."""
import os
from typing import List, Any
from langchain_core.documents import Document
from brevia.index import add_document
from brevia.load_file import read


def index_file_folder(
    file_path: str,
    collection: str,
    **kwargs: Any,
) -> int:
    """ Load documents in collection index from a file or folder """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} does not exist.")

    chunks_num = 0
    docs = load_file_folder_documents(file_path=file_path, **kwargs)
    for doc in docs:
        chunks_num += add_document(
            document=doc,
            collection_name=collection,
        )

    return chunks_num


def load_file_folder_documents(file_path: str, **kwargs: Any) -> List[Document]:
    """Load documents from file or folder"""
    if os.path.isdir(file_path):
        docs = []
        for file in os.listdir(file_path):
            docs.append(Document(
                page_content=read(file_path=f'{file_path}/{file}', **kwargs),
                metadata={'type': 'files', 'path': file_path},
            ))
        return docs

    doc = Document(
        page_content=read(file_path=file_path, **kwargs),
        metadata={'type': 'files', 'path': file_path},
    )

    return [doc]
