"""Query module tests"""
from brevia.query import load_qa_prompt, load_condense_prompt
from langchain.prompts import BasePromptTemplate

FAKE_PROMPT = {
    '_type': 'prompt',
    'input_variables': [],
    'template': 'Fake',
}


def test_load_qa_prompt():
    """Test load_qa_prompt method"""
    result = load_qa_prompt({
        'system': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

    result = load_qa_prompt({
        'human': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)


def test_load_condense_prompt():
    """Test load_condense_prompt method"""
    result = load_condense_prompt({
        'few': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

    result = load_condense_prompt({
        'condense': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)
