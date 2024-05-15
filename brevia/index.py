"""Index document with embeddings in vector database."""
from os import path
from logging import getLogger
from langchain.docstore.document import Document
from langchain.text_splitter import NLTKTextSplitter
from langchain.vectorstores.pgvector import PGVector
from langchain_community.vectorstores.pgembedding import CollectionStore
from langchain_community.vectorstores.pgembedding import EmbeddingStore
from sqlalchemy.orm import Session
from brevia import connection, load_file
from brevia.collections import single_collection_by_name
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
    texts = split_document(document)
    PGVector.from_documents(
        embedding=load_embeddings(collection_embeddings(collection_name)),
        documents=texts,
        collection_name=collection_name,
        connection_string=connection.connection_string(),
        ids=[document_id] * len(texts),
        use_jsonb=True,
    )

    return len(texts)


def collection_embeddings(collection_name: str) -> dict | None:
    """ Return custom embeddings of a collection"""
    collection = single_collection_by_name(collection_name)
    if collection is None:
        return None

    return collection.cmetadata.get('embeddings', None)


def split_document(document: Document):
    """ Split document into text chunks and return a list of documents"""
    settings = get_settings()
    text_splitter = NLTKTextSplitter(
        separator="\n",
        chunk_size=settings.text_chunk_size,
        chunk_overlap=settings.text_chunk_overlap
    )
    texts = text_splitter.split_documents([document])
    counter = 1
    for text in texts:
        text.metadata['part'] = counter
        counter += 1
    return texts


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
            if item['custom_id'] not in docs:
                docs.append(item['custom_id'])
                result.append(item)

        return result


def update_links_documents(collection_name: str) -> int:
    """ Update links document contents of a collection, if changed"""
    log = getLogger(__file__)
    log.info('Updating links contents in "%s"', collection_name)
    collection = single_collection_by_name(collection_name)
    if collection is None:
        log.error('Collection "%s" not found', collection_name)
        return 0
    docs_meta = documents_metadata(collection_id=collection.uuid,
                                   filter={'type': 'links'})
    count = 0
    for doc in docs_meta:
        res = update_collection_link(
            collection=collection,
            document_id=doc['custom_id'],
            document_medatata=doc['cmetadata']
        )
        count += 1 if res else 0

    return count


def update_collection_link(collection: CollectionStore, document_id: str,
                           document_medatata: dict) -> bool:
    """ Update a document link in a collection"""
    log = getLogger(__file__)
    url = document_medatata.get('url')
    if not url:
        log.error('Document "%s" has no URL metadata', document_id)
        return False

    options = select_load_link_options(
        url=url,
        options=collection.cmetadata.get('link_load_options', [])
    )
    text = load_file.read_html_url(url=url, **options)
    document = Document(page_content=text, metadata=document_medatata)
    if document_has_changed(document=document, collection_id=collection.uuid,
                            document_id=document_id):
        remove_document(collection_id=collection.uuid, document_id=document_id)
        add_document(document=document, collection_name=collection.name,
                     document_id=document_id)
        return True

    return False


def document_has_changed(document: Document, collection_id: str, document_id: str):
    """ Check if a document has changed """
    stored_docs = read_document(collection_id=collection_id, document_id=document_id)
    stored_docs.sort(key=lambda x: x['cmetadata'].get('part', 0))

    splitted = split_document(document)
    if len(stored_docs) != len(splitted):
        return True
    for i, stored_doc in enumerate(stored_docs):
        if stored_doc['document'] != splitted[i].page_content:
            return True
        if stored_doc['cmetadata'] != splitted[i].metadata:
            return True

    return False


def select_load_link_options(url: str, options: list):
    """ Select load link options for a given URL"""
    item = next((x for x in options if url == x['url']), None)
    if item:
        return {'selector': item.get('selector', '')}

    item = next((x for x in options if url.startswith(x['url'])), None)
    if item:
        return {'selector': item.get('selector', '')}

    return {}
