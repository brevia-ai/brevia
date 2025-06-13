"""Query module tests"""
from langchain.chains.base import Chain
from brevia.completions import simple_completion_chain, CompletionParams
from brevia.models import get_model_config


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


def test_get_model_config():
    """Test get_model_config functionality"""
    # Test data using qa_completion_llm which exists in settings
    test_key = "qa_completion_llm"
    test_user_config = {
        "qa_completion_llm": {"model": "from_user"}
    }
    test_db_config = {
        "qa_completion_llm": {"model": "from_db"}
    }
    test_default = {"model": "default"}

    # Test user config priority
    result = get_model_config(
        test_key,
        user_config=test_user_config,
        db_metadata=test_db_config,
        default=test_default
    )
    assert result == {"model": "from_user"}

    # Test db config fallback
    result = get_model_config(
        test_key,
        user_config=None,
        db_metadata=test_db_config,
        default=test_default
    )
    assert result == {"model": "from_db"}

    # Test default fallback when key not in settings
    result = get_model_config(
        "non_existent_key",
        user_config=None,
        db_metadata=None,
        default=test_default
    )
    assert result == test_default
