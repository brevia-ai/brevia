"""chat_history module tests"""
from datetime import datetime, timedelta
import uuid
import pytest
from brevia.chat_history import (
    history,
    add_history,
    history_from_db,
    get_history,
    ChatHistoryFilter,
)
from brevia.collections import create_collection


def test_history():
    """ Test history() function """
    result = history([])
    assert result == []
    result = history([{'query': 'my query', 'answer': 'your answer'}])
    assert result == [('my query', 'your answer')]
    result = history([], uuid.uuid4())
    assert result == []


def test_add_history():
    """Test add_history function"""
    assert add_history('123', 'test', 'who?', 'me') is None
    create_collection('test_collection', {})
    history_item = add_history(uuid.uuid4(), 'test_collection', 'who?', 'me')
    assert history_item is not None
    assert history_item.question == 'who?'
    assert history_item.answer == 'me'


def test_add_history_failure():
    """Test add_history with non-existent collection"""
    session_id = uuid.uuid4()
    # When collection doesn't exist, it should
    # still add the history but with collection_id = None
    history_item = add_history(session_id, 'non_existent_collection', 'who?', 'me')
    assert history_item is not None
    assert history_item.collection_id is None
    assert history_item.question == 'who?'
    assert history_item.answer == 'me'


def test_get_history():
    """Test get_history function"""
    history_items = get_history(filter=ChatHistoryFilter())
    expected = {
        'data': [],
        'meta': {
            'pagination': {
                'count': 0,
                'page': 1,
                'page_count': 0,
                'page_items': 0,
                'page_size': 50,
            },
        }
    }
    assert history_items == expected


def test_get_history_filters():
    """Test get_history filters"""
    create_collection('test_collection', {})
    session_id = uuid.uuid4()
    add_history(session_id, 'test_collection', 'who?', 'me')
    today = datetime.strftime(datetime.now(), '%Y-%m-%d')
    yesterday = datetime.strftime(datetime.now() - timedelta(1), '%Y-%m-%d')
    tomorrow = datetime.strftime(datetime.now() + timedelta(1), '%Y-%m-%d')
    result = get_history(ChatHistoryFilter(max_date=today))
    assert result['meta']['pagination']['count'] == 1
    result = get_history(ChatHistoryFilter(min_date=yesterday))
    assert result['meta']['pagination']['count'] == 1
    result = get_history(ChatHistoryFilter(min_date=tomorrow))
    assert result['meta']['pagination']['count'] == 0
    result = get_history(ChatHistoryFilter(max_date=tomorrow))
    assert result['meta']['pagination']['count'] == 1
    result = get_history(ChatHistoryFilter(
        min_date=yesterday, collection='test_collection'
    ))
    assert result['meta']['pagination']['count'] == 1
    result = get_history(ChatHistoryFilter(min_date=tomorrow, max_date=tomorrow))
    assert result['meta']['pagination']['count'] == 0
    result = get_history(ChatHistoryFilter(min_date=yesterday, collection='test2'))
    assert result['meta']['pagination']['count'] == 0
    result = get_history(ChatHistoryFilter(session_id=str(session_id)))
    assert result['meta']['pagination']['count'] == 1
    result = get_history(ChatHistoryFilter(session_id=str(uuid.uuid4())))
    assert result['meta']['pagination']['count'] == 0


def test_history_from_db():
    """Test history_from_db function"""
    result = history_from_db(uuid.uuid4())
    assert result == []
    create_collection('test_collection', {})
    session_id = uuid.uuid4()
    add_history(session_id, 'test_collection', 'who?', 'me')
    result = history_from_db(session_id)
    assert len(result) == 1
    assert result[0] == ('who?', 'me')
