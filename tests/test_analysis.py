"""Analysis module tests"""
from langchain.prompts import BasePromptTemplate
from brevia.analysis import load_summarize_prompt

FAKE_PROMPT = {
    '_type': 'prompt',
    'input_variables': [],
    'template': 'Fake',
}


def test_load_summarize_prompt():
    """Test load_summarize_prompt method"""
    result = load_summarize_prompt(FAKE_PROMPT)
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

