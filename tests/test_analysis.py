"""Analysis module tests"""
from brevia.analysis import load_summarize_prompt
from langchain.prompts import BasePromptTemplate

FAKE_PROMPT = {
    '_type': 'prompt',
    'input_variables': [],
    'template': 'Fake',
}


def test_load_summarize_prompt():
    """Test load_summarize_prompt method"""
    result = load_summarize_prompt({
        'custom': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

    result = load_summarize_prompt({
        'summarize': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

    result = load_summarize_prompt({
        'summarize_point': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)

    result = load_summarize_prompt({
        'classification': FAKE_PROMPT,
    })
    assert result is not None
    assert isinstance(result, BasePromptTemplate)
