"""chat_history module tests"""
from datetime import datetime, timedelta
import uuid
import pytest
from brevia.chat_history import (
    history,
    add_history,
    history_from_db,
    get_history,
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
    history = add_history(uuid.uuid4(), 'test_collection', 'who?', 'me')
    assert history is not None
    assert history.question == 'who?'
    assert history.answer == 'me'


def test_add_history_failure():
    """Test history_from_db failure"""
    with pytest.raises(ValueError) as exc:
        add_history(uuid.uuid4(), 'test', 'who?', 'me')
    assert str(exc.value) == 'Collection not found'


def test_get_history():
    """Test get_history function"""
    history_items = get_history()
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
    yesterday = datetime.strftime(datetime.now() - timedelta(1), '%Y-%m-%d')
    tomorrow = datetime.strftime(datetime.now() + timedelta(1), '%Y-%m-%d')
    result = get_history(min_date=yesterday)
    assert result['meta']['pagination']['count'] == 1
    result = get_history(min_date=tomorrow)
    assert result['meta']['pagination']['count'] == 0
    result = get_history(max_date=tomorrow)
    assert result['meta']['pagination']['count'] == 1
    result = get_history(min_date=yesterday, collection='test_collection')
    assert result['meta']['pagination']['count'] == 1
    result = get_history(min_date=tomorrow, max_date=tomorrow)
    assert result['meta']['pagination']['count'] == 0
    result = get_history(min_date=yesterday, collection='test2')
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
