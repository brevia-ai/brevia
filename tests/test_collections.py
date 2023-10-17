"""collections module tests"""
import uuid
from brevia.collections import (
    collections_info,
    collection_name_exists,
    collection_exists,
    create_collection,
    update_collection,
    delete_collection,
    single_collection
)


def test_create_collection():
    """ Test create_collection function """
    result = create_collection('test_collection', {'key': 'value'})
    assert result.uuid is not None
    assert result.name == 'test_collection'
    assert result.cmetadata == {'key': 'value'}


def test_collections_info():
    """Test collections_info()"""
    result = collections_info()
    assert result == []


def test_collection_name_exists():
    """Test collection_name_exists function"""
    create_collection('test_collection2', {})
    assert collection_name_exists('test_collection2') is True
    assert collection_name_exists('nonexistent_collection') is False


def test_collection_exists():
    """Test collection_exists function"""
    collection = create_collection('new_collection', {})
    assert collection_exists(collection.uuid) is True
    assert collection_exists(uuid.uuid4()) is False


def test_update_collection():
    """Test update_collection function"""
    collection = create_collection('new_collection', {})
    update_collection(collection.uuid, 'updated_collection', {'new_key': 'new_value'})
    updated = single_collection(collection.uuid)
    assert updated.name == 'updated_collection'
    assert updated.cmetadata == {'new_key': 'new_value'}


def test_delete_collection():
    """Test delete_collection function"""
    collection = create_collection('new_collection', {})
    delete_collection(collection.uuid)
    assert collection_name_exists('new_collection') is False
