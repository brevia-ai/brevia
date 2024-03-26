"""Index document with embeddings in vector database."""
from os import path
from langchain.docstore.document import Document
from langchain.text_splitter import NLTKTextSplitter
from langchain.vectorstores.pgvector import PGVector
from langchain_community.vectorstores.pgembedding import EmbeddingStore
from sqlalchemy.orm import Session
from brevia import connection, load_file
from brevia.models import load_embeddings
from brevia.settings import get_settings
from brevia.utilities.json_api import query_data_pagination


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
    if not path.isfile(file_path):
        raise FileNotFoundError(file_path)

    text = load_file.read_pdf_file(
        file_path=file_path,
        page_from=page_from,
        page_to=page_to,
    )
    if metadata is None:
        metadata = {'source': path.basename(file_path)}

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
    settings = get_settings()
    text_splitter = NLTKTextSplitter(
        separator="\n",
        chunk_size=settings.text_chunk_size,
        chunk_overlap=settings.text_chunk_overlap
    )
    texts = text_splitter.split_documents([document])

    PGVector.from_documents(
        embedding=load_embeddings(),
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


def metadata_filters(filter: dict[str, str] = {}):
    """
        Returns a list of metadata to be use as query filter in embeddings table
    """
    res = []
    for key in filter.keys():
        res.append(EmbeddingStore.cmetadata[key].astext == str(filter[key]))
    return res


def collection_documents(
    collection_id: str,
    filter: dict[str, str] = {},
    page: int = 1,
    page_size: int = 50,
):
    """ Read document `document_id` from collection index"""
    query_filters = [EmbeddingStore.collection_id == collection_id]
    query_filters.extend(metadata_filters(filter=filter))
    with Session(connection.db_connection()) as session:
        query = session.query(
            EmbeddingStore.document,
            EmbeddingStore.cmetadata,
            EmbeddingStore.custom_id
        )
        query = query.filter(*query_filters)
        return query_data_pagination(query=query, page=page, page_size=page_size)


def update_metadata(
    collection_id: str,
    document_id: str,
    metadata: dict | None = None,
):
    """ Update metadata of a document in a collection"""
    filter_document = EmbeddingStore.custom_id == document_id
    filter_collection = EmbeddingStore.collection_id == collection_id
    with Session(connection.db_connection()) as session:
        query = session.query(EmbeddingStore).filter(filter_collection, filter_document)
        query.update({EmbeddingStore.cmetadata: metadata})
        session.commit()


def documents_metadata(
    collection_id: str,
    filter: dict[str, str] = {},
    document_id: str = None,
):
    """ Read documents metadata of a collection"""
    query_filters = [EmbeddingStore.collection_id == collection_id]
    if document_id:
        query_filters.append(EmbeddingStore.custom_id == document_id)
    query_filters.extend(metadata_filters(filter=filter))
    with Session(connection.db_connection()) as session:
        query = session.query(EmbeddingStore.custom_id, EmbeddingStore.cmetadata)
        query = query.filter(*query_filters)
        result = []
        docs = []
        for row in query.all():
            item = row._asdict()
            if (item['custom_id'] not in docs):
                docs.append(item['custom_id'])
                result.append(item)

        return result
