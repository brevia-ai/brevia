"""Callback module tests"""
from uuid import uuid4
from json import loads
from langchain.docstore.document import Document
from brevia.callback import ConversationCallbackHandler, TokensCallbackHandler
from brevia.collections import create_collection


def test_chain_result():
    """Test chain_result method"""
    callback = ConversationCallbackHandler()
    callback.result = {
        'answer': 'I don\'t know',
        'source_documents': [Document(page_content='', metadata={})],
    }
    create_collection('new_collection', {})
    result = callback.chain_result(
        callb=TokensCallbackHandler(),
        collection='new_collection',
        question='who are you?',
        x_chat_session=uuid4(),

    )
    assert result is not None
    item = loads(result)
    assert len(item) == 2
    assert 'chat_history_id' in item[0]
    assert 'page_content' in item[1]
