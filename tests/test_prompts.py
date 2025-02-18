"""Prompts module tests"""
from langchain_core.prompts import (
    ChatPromptTemplate,
    BasePromptTemplate,
    PromptTemplate,
)
from brevia.prompts import load_condense_prompt, load_qa_prompt


def test_load_qa_prompt():
    """Test load_qa_prompt method"""
    result = load_qa_prompt()
    assert result is not None
    assert isinstance(result, ChatPromptTemplate)
    assert len(result.messages) == 2

    human = {
        '_type': 'prompt',
        'input_variables': ['question'],
        'template': 'Question: {question}',
    }
    system = {
        '_type': 'prompt',
        'input_variables': ['context', 'lang'],
        'template':
            """
            As an AI assistant your task is to provide valuable information
            to our users. Answer the question using the provided context between
            ##Context start## and ##Context end##.
            ##Context start## {{context}} ##Context end##
            Answer in {{ lang }}
            """
    }

    result = load_qa_prompt(prompts={'human': human, 'system': system})
    assert result is not None
    assert isinstance(result, ChatPromptTemplate)
    assert len(result.messages) == 2


def test_load_condense_prompt():
    """Test load_condense_prompt method"""
    result = load_condense_prompt()
    assert result is not None
    assert isinstance(result, PromptTemplate)
    assert result.template is not None

    config = {
        '_type': 'prompt',
        'input_variables': ['question', 'chat_history'],
        'template':
            """
            Given the following conversation and a "follow-up question",
            rephrase the "follow-up question" to be a "standalone question"
            \n\nconversation:\n\n{chat_history}\n
            follow-up question: {question}\n\n
            """,
    }
    result = load_condense_prompt(config=config)
    assert result is not None
    assert isinstance(result, BasePromptTemplate)
