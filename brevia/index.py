"""Index document with embeddings in vector database."""
import os
import logging
from langchain.docstore.document import Document
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.embeddings.fake import FakeEmbeddings
from langchain.text_splitter import NLTKTextSplitter
from langchain.vectorstores.pgvector import PGVector
from langchain.vectorstores._pgvector_data_models import EmbeddingStore
from sqlalchemy.orm import Session
from brevia import connection, load_file


def init_index():
    """Init index data"""
    try:
        import nltk  # pylint: disable=import-outside-toplevel
        nltk.download('punkt')

    except ImportError as exc:
        raise ImportError(
            "NLTK is not installed!"
        ) from exc


def load_pdf_file(
    # pylint: disable=too-many-arguments
    file_path: str,
    collection_name: str,
    document_id: str | None = None,
    metadata: dict | None = None,
    page_from: int = None,  # from page, used in PDF
    page_to: int = None,  # to page, used in PDF
) -> int:
    """
    Load document from PDF file, add document to collection index
    and return number of splitted text chunks
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    text = load_file.read_pdf_file(
        file_path=file_path,
        page_from=page_from,
        page_to=page_to,
    )
    if metadata is None:
        metadata = {'source': os.path.basename(file_path)}

    return add_document(
        document=Document(
            page_content=text,
            metadata=metadata,
        ),
        collection_name=collection_name,
        document_id=document_id,
    )


def add_document(
    document: Document,
    collection_name: str,
    document_id: str = None,
) -> int:
    """ Add document to index and return number of splitted text chunks"""
    text_splitter = NLTKTextSplitter(
        separator="\n",
        chunk_size=int(os.environ.get('TEXT_CHUNK_SIZE', 2000)),
        chunk_overlap=int(os.environ.get('TEXT_CHUNK_OVERLAP', 200))
    )
    texts = text_splitter.split_documents([document])

    PGVector.from_documents(
        embedding=get_embeddings(),
        documents=texts,
        collection_name=collection_name,
        connection_string=connection.connection_string(),
        ids=[document_id] * len(texts),
    )

    return len(texts)


def remove_document(
    collection_id: str,
    document_id: str,
):
    """ Remove document `document_id` from collection index"""
    filter_document = EmbeddingStore.custom_id == document_id
    filter_collection = EmbeddingStore.collection_id == collection_id
    with Session(connection.db_connection()) as session:
        query = session.query(EmbeddingStore).filter(filter_collection, filter_document)
        query.delete()
        session.commit()


def read_document(
    collection_id: str,
    document_id: str,
):
    """ Read document `document_id` from collection index"""
    filter_document = EmbeddingStore.custom_id == document_id
    filter_collection = EmbeddingStore.collection_id == collection_id
    with Session(connection.db_connection()) as session:
        query = session.query(EmbeddingStore.document, EmbeddingStore.cmetadata)
        query = query.filter(filter_collection, filter_document)
        return [row._asdict() for row in query.all()]


def get_embeddings() -> (FakeEmbeddings | OpenAIEmbeddings):
    """ Get Embeddings engine: Fake or OpenAI for now """
    if bool(os.environ.get("FAKE_EMBEDDING")):
        print('Using FAKE embeddings!!')
        logging.getLogger(__name__).warning('Using FAKE summary - text truncate!!')
        return FakeEmbeddings(size=1536)

    return OpenAIEmbeddings()
