"""Prompts module tests"""
from pathlib import Path
import pytest
from langchain_core.prompts import (
    ChatPromptTemplate,
    BasePromptTemplate,
    PromptTemplate,
    FewShotPromptTemplate,
)
from brevia.prompts import load_condense_prompt, load_prompt_from_yaml, load_qa_prompt
from brevia.settings import get_settings
from tests.tasks.test_text_analysys import FILES_PATH


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


FILES_PATH = f'{Path(__file__).parent}/files'


def test_load_prompt_from_yaml_fail():
    """Test load_prompt_from_yaml failure"""
    with pytest.raises(FileNotFoundError) as exc:
        load_prompt_from_yaml('not.found')
    assert 'No such file or directory' in str(exc.value)

    settings = get_settings()
    current_path = settings.prompts_base_path
    settings.prompts_base_path = f'{FILES_PATH}/prompts'
    with pytest.raises(ValueError) as exc:
        load_prompt_from_yaml('empty.yml')
    assert str(exc.value).startswith('Failed to load prompt from')

    settings.prompts_base_path = current_path


def test_load_prompt_from_yaml_few_shot():
    """Test load_prompt_from_yaml of a 'few_shot' prompt"""
    settings = get_settings()
    current_path = settings.prompts_base_path
    settings.prompts_base_path = f'{FILES_PATH}/prompts'
    result = load_prompt_from_yaml('few_shot.yml')
    assert result is not None
    assert isinstance(result, FewShotPromptTemplate)

    settings.prompts_base_path = current_path
