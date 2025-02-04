"""collections module tests (deprecated)"""
from brevia.collections import (
    collections_info,
    collection_name_exists,
    collection_exists,
    create_collection,
    update_collection,
    delete_collection,
    single_collection,
    single_collection_by_name,
)


def test_collection_module():
    """ Test deprecated `collections` module function"""
    result = collections_info()
    assert result == []
    result = create_collection('test_collection', {'key': 'value'})
    assert result.uuid is not None
    assert result.name == 'test_collection'
    assert result.cmetadata == {'key': 'value'}
    update_collection(result.uuid, 'updated_collection', {'new_key': 'new_value'})
    updated = single_collection(result.uuid)
    assert updated.name == 'updated_collection'
    assert updated.cmetadata == {'new_key': 'new_value'}
    coll = single_collection_by_name('updated_collection')
    assert coll.uuid == result.uuid
    assert collection_exists(result.uuid)
    delete_collection(result.uuid)
    assert collection_name_exists('new_collection') is False
