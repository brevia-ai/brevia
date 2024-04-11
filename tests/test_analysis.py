"""Analysis module tests"""
import pytest
from brevia.analysis import (
    load_stuff_prompts,
    load_map_prompts,
    load_refine_prompts,
    summarize
)
from brevia.models import LOREM_IPSUM

FAKE_INITIAL_PROMPT = {
    'initial_prompt': {
        '_type': 'prompt',
        'input_variables': [],
        'template': 'Fake',
    }
}

FAKE_COMPLEX_PROMPT = {
    'initial_prompt': {
        '_type': 'prompt',
        'input_variables': [],
        'template': 'Fake',
    },
    'iteration_prompt': {
        '_type': 'prompt',
        'input_variables': [],
        'template': 'Fake',
    }
}


def test_load_stuff_prompts():
    """Test load_summarize_prompts method"""
    result = load_stuff_prompts(FAKE_INITIAL_PROMPT)
    assert result is not None
    assert isinstance(result, dict)


def test_load_map_prompts_one():
    """Test load_summarize_prompts method with one prompt"""
    result = load_map_prompts(FAKE_INITIAL_PROMPT)
    assert result is not None
    assert isinstance(result, dict)


def test_load_map_prompts_both():
    """Test load_summarize_prompts method with two prompts"""
    result = load_map_prompts(FAKE_COMPLEX_PROMPT)
    assert result is not None
    assert isinstance(result, dict)


def test_load_refine_prompts_one():
    """Test load_summarize_prompts method with one prompt"""
    result = load_refine_prompts(FAKE_INITIAL_PROMPT)
    assert result is not None
    assert isinstance(result, dict)


def test_load_refine_prompts_both():
    """Test load_summarize_prompts method with two prompts"""
    result = load_refine_prompts(FAKE_COMPLEX_PROMPT)
    assert result is not None
    assert isinstance(result, dict)


def test_summarize():
    """Test summarize function"""
    result = summarize(text='A very long text')
    assert result['output_text'] == LOREM_IPSUM


def test_summarize_fail():
    """Test summarize failure"""
    with pytest.raises(ValueError) as exc:
        summarize(text='A very long text', chain_type='wrong-chain')
    msg = 'Got unsupported chain type: wrong-chain. Should be one of '
    print(exc.value)
    assert str(exc.value) == msg + "['stuff', 'map_reduce', 'refine']"
