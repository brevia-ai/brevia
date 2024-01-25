"""API endpoints definitions to handle Collections"""
from fastapi import APIRouter
from pydantic import BaseModel
from brevia.dependencies import (
    get_dependencies,
    check_collection_name_absent,
    check_collection_uuid
)
from brevia import collections

router = APIRouter()


@router.get(
    '/collections',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Collections'],
)
async def collections_index(name: str | None = None):
    """ GET /collections endpoint, information on available collections """
    return collections.collections_info(collection=name)


@router.get(
    '/collections/{uuid}',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Collections'],
)
async def read_collection(uuid: str):
    """ GET /collections/{uuid} endpoint"""
    check_collection_uuid(uuid)

    return collections.single_collection(uuid)


class CollectionBody(BaseModel):
    """ Collection creation model """
    name: str
    cmetadata: dict


@router.post(
    '/collections',
    status_code=201,
    dependencies=get_dependencies(),
    tags=['Collections'],
)
def create_collection(body: CollectionBody):
    """ POST /collections endpoint"""
    check_collection_name_absent(body.name)

    return collections.create_collection(
        name=body.name,
        cmetadata=body.cmetadata,
    )


@router.patch(
    '/collections/{uuid}',
    status_code=204,
    dependencies=get_dependencies(),
    tags=['Collections'],
)
def update_collection(uuid: str, body: CollectionBody):
    """ PATCH /collections endpoint"""
    check_collection_uuid(uuid)
    current = collections.single_collection(uuid)
    if current.name != body.name:
        # if name is changed check that it's not in use
        check_collection_name_absent(body.name)

    collections.update_collection(uuid=uuid, name=body.name, cmetadata=body.cmetadata)


@router.delete(
    '/collections/{uuid}',
    status_code=204,
    dependencies=get_dependencies(json_content_type=False),
    tags=['Collections'],
)
def delete_collection(uuid: str):
    """ DELETE /collections endpoint"""
    check_collection_uuid(uuid)
    collections.delete_collection(uuid)
