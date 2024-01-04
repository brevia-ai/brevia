"""API endpoints definitions for indexing actions"""
from typing import Annotated
from os import path
import json
import logging
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status, UploadFile, Form
from langchain.docstore.document import Document
from langchain.vectorstores._pgvector_data_models import CollectionStore
from brevia.dependencies import get_dependencies, save_upload_file_tmp
from brevia import index, collections, load_file

router = APIRouter()


class IndexBody(BaseModel):
    """ /index request body """
    content: str
    collection_id: str
    document_id: str
    metadata: dict = {}


@router.post('/index', status_code=204, dependencies=get_dependencies())
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
    dependencies=get_dependencies(json_content_type=False)
)
def upload_and_index(
    file: UploadFile,
    collection_id: Annotated[str, Form()],
    document_id: Annotated[str, Form()],
    metadata: Annotated[str | None, Form()] = None,
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

    text = load_file.read(file_path=tmp_path)
    index.add_document(
        document=Document(
            page_content=text,
            metadata=metadata,
        ),
        collection_name=collection.name,
        document_id=document_id,
    )


@router.delete(
    '/index/{collection_id}/{document_id}',
    status_code=204,
    dependencies=get_dependencies(json_content_type=False)
)
def remove_document(collection_id: str, document_id: str):
    """ Remove document from collection index """
    index.remove_document(
        collection_id=collection_id,
        document_id=document_id,
    )


@router.get(
    '/index/{collection_id}/{document_id}',
    dependencies=get_dependencies(json_content_type=False)
)
def read_document(collection_id: str, document_id: str):
    """ Read document from collection index """
    return index.read_document(
        collection_id=collection_id,
        document_id=document_id,
    )
