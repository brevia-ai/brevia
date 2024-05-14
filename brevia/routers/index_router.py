"""API endpoints definitions for indexing actions"""
from typing import Annotated
from os import path
import json
import re
import logging
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, status, UploadFile, Form
from langchain.docstore.document import Document
from langchain_community.vectorstores.pgembedding import CollectionStore
from brevia.dependencies import (
    get_dependencies,
    save_upload_file_tmp,
    check_collection_uuid,
)
from brevia import index, collections, load_file

router = APIRouter()


class IndexBody(BaseModel):
    """ /index request body """
    content: str
    collection_id: str
    document_id: str
    metadata: dict = {}


@router.post(
    '/index',
    status_code=204,
    dependencies=get_dependencies(),
    tags=['Index'],
)
def index_document(item: IndexBody):
    """ Add single document to collection index """
    collection = load_collection(collection_id=item.collection_id)
    # remove same document if already indexed
    index.remove_document(
        collection_id=item.collection_id,
        document_id=item.document_id,
    )
    index.add_document(
        document=Document(page_content=item.content, metadata=item.metadata),
        collection_name=collection.name,
        document_id=item.document_id,
    )


def load_collection(collection_id: str) -> CollectionStore:
    """ Load collection by ID and throw 404 if not found"""
    collection = collections.single_collection(collection_id)
    if collection is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Collection id '{collection_id}' was not found",
        )
    return collection


@router.post(
    '/index/upload',
    status_code=204,
    dependencies=get_dependencies(json_content_type=False),
    tags=['Index'],
)
def upload_and_index(
    file: UploadFile,
    collection_id: Annotated[str, Form()],
    document_id: Annotated[str, Form()],
    metadata: Annotated[str | None, Form()] = None,
    options: Annotated[str | None, Form()] = None,
):
    """
    Upload a PDF file and perform index on a collection
    """
    collection = load_collection(collection_id=collection_id)
    log = logging.getLogger(__name__)
    log.info("Uploaded '%s' - %s - %s", file.filename, file.content_type, file.size)
    log.info("Collection '%s' - document %s", collection.name, document_id)
    if file.content_type not in ['application/pdf', 'text/plain']:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'Unsupported file content type "{file.content_type}"',
        )
    tmp_path = save_upload_file_tmp(file)
    if metadata is not None:
        metadata = json.loads(metadata)
    else:
        metadata = {'source': path.basename(tmp_path)}

    # remove same document if already indexed
    index.remove_document(
        collection_id=collection_id,
        document_id=document_id,
    )
    read_options = {} if options is None else json.loads(options)
    text = load_file.read(file_path=tmp_path, **read_options)
    index.add_document(
        document=Document(
            page_content=text,
            metadata=metadata,
        ),
        collection_name=collection.name,
        document_id=document_id,
    )


class IndexLink(BaseModel):
    """ /index/link request body """
    link: str  # link to a webpage
    collection_id: str
    document_id: str
    metadata: dict = {}
    options: dict = {}


@router.post(
    '/index/link',
    status_code=204,
    dependencies=get_dependencies(json_content_type=False),
    tags=['Index'],
)
def parse_link_and_index(item: IndexLink):
    """
    Add a web page content to a collection index
    """
    collection = load_collection(collection_id=item.collection_id)
    log = logging.getLogger(__name__)
    log.info(
        "Adding link '%s' to collection '%s' / document '%s'",
        item.link,
        collection.name,
        item.document_id
    )

    text = load_file.read_html_url(url=item.link, **item.options)
    if not text:
        return
    # remove same document if already indexed
    index.remove_document(
        collection_id=item.collection_id,
        document_id=item.document_id,
    )
    index.add_document(
        document=Document(
            page_content=text,
            metadata=item.metadata,
        ),
        collection_name=collection.name,
        document_id=item.document_id,
    )


@router.delete(
    '/index/{collection_id}/{document_id}',
    status_code=204,
    dependencies=get_dependencies(json_content_type=False),
    tags=['Index'],
)
def remove_document(collection_id: str, document_id: str):
    """ Remove document from collection index """
    index.remove_document(
        collection_id=collection_id,
        document_id=document_id,
    )


def read_filter(request: Request) -> dict:
    """Read metadata filter dict from query string"""
    result = {}
    regexp = r'filter\[(.*?)\]'
    for key in request.query_params.keys():
        if re.match(regexp, key):
            f_key = re.search(regexp, key).group(1)
            result[f_key] = request.query_params.get(key)

    return result


@router.get(
    '/index/{collection_id}',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Index'],
)
def index_docs(
    collection_id: str,
    request: Request,
    page: int = 1,
    page_size: int = 50
):
    """ Read collection documents with metadata filter """
    load_collection(collection_id=collection_id)
    return index.collection_documents(
        collection_id=collection_id,
        filter=read_filter(request=request),
        page=page,
        page_size=page_size,
    )


@router.get(
    '/index/{collection_id}/documents_metadata',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Index'],
)
def index_docs_metadata(collection_id: str, request: Request):
    """ Read collection documents metadata"""
    load_collection(collection_id=collection_id)
    return index.documents_metadata(
        collection_id=collection_id,
        filter=read_filter(request=request),
        document_id=request.query_params.get('document_id'),
    )


@router.get(
    '/index/{collection_id}/{document_id}',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Index'],
)
def read_document(collection_id: str, document_id: str):
    """ Read single document from collection index """
    return index.read_document(
        collection_id=collection_id,
        document_id=document_id,
    )


class IndexMetaBody(BaseModel):
    """ /index/metadata request body """
    collection_id: str
    document_id: str
    metadata: dict = {}


@router.post('/index/metadata', status_code=204, dependencies=get_dependencies())
def index_metadata_document(item: IndexMetaBody):
    """ Update metadata of a single document in a collection"""
    check_collection_uuid(item.collection_id)
    index.update_metadata(
        collection_id=item.collection_id,
        document_id=item.document_id,
        metadata=item.metadata,
    )
