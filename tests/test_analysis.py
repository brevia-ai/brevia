"""Analysis module tests"""
import pytest
from langchain.prompts import BasePromptTemplate
from brevia.analysis import load_summarize_prompt, summarize
from brevia.models import LOREM_IPSUM

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


def test_summarize():
    """Test summarize function"""
    result = summarize(text='A very long text')
    assert result == LOREM_IPSUM


def test_summarize_fail():
    """Test summarize failure"""
    with pytest.raises(ValueError) as exc:
        summarize(text='A very long text', chain_type='wrong-chain')
    msg = 'Got unsupported chain type: wrong-chain. Should be one of '
    print(exc.value)
    assert str(exc.value) == msg + "['stuff', 'map_reduce', 'refine']"
