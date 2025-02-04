"""API endpoints definitions to handle Collections"""
from fastapi import APIRouter
from pydantic import BaseModel
from brevia.dependencies import (
    get_dependencies,
    check_collection_name_absent,
    check_collection_uuid
)
from brevia.collections_tools import (
    collections_info,
    create_collection,
    update_collection,
    delete_collection,
    single_collection,
)

router = APIRouter()


@router.get(
    '/collections',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Collections'],
)
async def collections_index(name: str | None = None):
    """ GET /collections endpoint, information on available collections """
    return collections_info(collection=name)


@router.get(
    '/collections/{uuid}',
    dependencies=get_dependencies(json_content_type=False),
    tags=['Collections'],
)
async def read_collection(uuid: str):
    """ GET /collections/{uuid} endpoint"""
    check_collection_uuid(uuid)

    return single_collection(uuid)


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
def add_collection(body: CollectionBody):
    """ POST /collections endpoint"""
    check_collection_name_absent(body.name)

    return create_collection(
        name=body.name,
        cmetadata=body.cmetadata,
    )


@router.patch(
    '/collections/{uuid}',
    status_code=204,
    dependencies=get_dependencies(),
    tags=['Collections'],
)
def change_collection(uuid: str, body: CollectionBody):
    """ PATCH /collections endpoint"""
    check_collection_uuid(uuid)
    current = single_collection(uuid)
    if current.name != body.name:
        # if name is changed check that it's not in use
        check_collection_name_absent(body.name)

    update_collection(uuid=uuid, name=body.name, cmetadata=body.cmetadata)


@router.delete(
    '/collections/{uuid}',
    status_code=204,
    dependencies=get_dependencies(json_content_type=False),
    tags=['Collections'],
)
def remove_collection(uuid: str):
    """ DELETE /collections endpoint"""
    check_collection_uuid(uuid)
    delete_collection(uuid)
