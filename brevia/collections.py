"""Collections handling functions"""
from langchain_community.vectorstores.pgembedding import CollectionStore
from sqlalchemy.orm import Session
from brevia import connection
from brevia.utilities.uuid import is_valid_uuid


def collections_info(collection: str | None = None):
    """ Retrieve collections data """
    filter_collection = CollectionStore.name == collection
    if collection is None:
        filter_collection = CollectionStore.name is not None

    with Session(connection.db_connection()) as session:
        query = (
            session.query(
                CollectionStore.uuid,
                CollectionStore.name,
                CollectionStore.cmetadata,
            )
            .filter(filter_collection)
            .limit(100)
        )

        result = [u._asdict() for u in query.all()]
        session.close()

    return result


def collection_name_exists(name: str) -> bool:
    """ Check if a collection name exists already """
    store = single_collection_by_name(name)

    return store is not None


def collection_exists(uuid: str) -> bool:
    """ Check if a collection uuid exists """
    store = single_collection(uuid)

    return store is not None


def single_collection(uuid: str) -> (CollectionStore | None):
    """ Get single collection by UUID """
    if not is_valid_uuid(uuid):
        return None
    with Session(connection.db_connection()) as session:
        return session.get(CollectionStore, uuid)


def single_collection_by_name(name: str) -> (CollectionStore | None):
    """ Get single collection by name"""
    with Session(connection.db_connection()) as session:
        return CollectionStore.get_by_name(session=session, name=name)


def create_collection(
    name: str,
    cmetadata: dict,
) -> CollectionStore:
    """ Create single collection """
    with Session(connection.db_connection()) as session:
        collection_store = CollectionStore(
            name=name,
            cmetadata=cmetadata,
        )
        session.expire_on_commit = False
        session.add(collection_store)
        session.commit()

        return collection_store


def update_collection(
    uuid: str,
    name: str,
    cmetadata: dict,
):
    """ Update single collection """
    with Session(connection.db_connection()) as session:
        collection = session.get(CollectionStore, uuid)
        collection.name = name
        collection.cmetadata = cmetadata
        session.add(collection)
        session.commit()


def delete_collection(
    uuid: str,
):
    """ Delete single collection """
    with Session(connection.db_connection()) as session:
        collection = session.get(CollectionStore, uuid)
        session.delete(collection)
        session.commit()
