"""Query module tests"""
from langchain.chains.base import Chain
from brevia.completions import simple_completion_chain, CompletionParams


fake_prompt = CompletionParams()
fake_prompt.prompt = {
    '_type': 'prompt',
    'input_variables': ['text'],
    'template': 'Fake',
}


def test_simple_completion_chain():
    """Test simple_completion_chain method"""
    result = simple_completion_chain(fake_prompt)
    assert result is not None
    assert isinstance(result, Chain)
