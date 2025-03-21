"""Test text analysis tasks"""
from pathlib import Path
import pytest
import yaml
from brevia.settings import get_settings
from brevia.tasks.text_analysis import RefineTextAnalysisTask
from brevia.tasks.text_analysis import SummarizeTextAnalysisTask
from brevia.prompts import (
    load_stuff_prompts,
    load_map_prompts,
    load_refine_prompts
)
from brevia.models import LOREM_IPSUM

FILES_PATH = f'{Path(__file__).parent.parent}/files'

FAKE_INITIAL_PROMPT = {
    '_type': 'prompt',
    'input_variables': [
        "text"
    ],
    'template': 'Fake {text}',
}

FAKE_ITERATION_PROMPT = {
    '_type': 'prompt',
    'input_variables': [
        "text"
    ],
    'template': 'Fake {text}',
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
    analysis = SummarizeTextAnalysisTask(
        text='A very long text',
        chain_type='stuff',
        initial_prompt=FAKE_INITIAL_PROMPT,
        iteration_prompt=FAKE_ITERATION_PROMPT,

    )
    result = analysis.perform_task()
    assert result['output_text'] == LOREM_IPSUM


def test_summarize_fail():
    """Test summarize failure"""
    with pytest.raises(ValueError) as exc:
        SummarizeTextAnalysisTask(
            text='A very long text',
            chain_type='wrong-chain',
            initial_prompt=FAKE_INITIAL_PROMPT,
            iteration_prompt=FAKE_ITERATION_PROMPT,
        )
    msg = 'Got unsupported chain type: wrong-chain. Should be one of '
    print(exc.value)
    assert str(exc.value) == msg + "['stuff', 'map_reduce', 'refine']"


def test_refine_text_analysis():
    """Test refine text analysis task"""
    settings = get_settings()
    current_path = settings.prompts_base_path
    settings.prompts_base_path = f'{FILES_PATH}/prompts'

    file_path = f'{FILES_PATH}/docs/test.txt'
    prompts = {
        'initial_prompt': 'initial_prompt.yml',
        'refine_prompt': 'refine_prompt.yml'
    }
    task = RefineTextAnalysisTask(file_path=file_path, prompts=prompts)
    result = task.perform_task()
    assert 'input_documents' in result
    assert 'output_text' in result
    # Restore `prompts_base_path` settings
    settings.prompts_base_path = current_path

    with open(f'{FILES_PATH}/prompts/initial_prompt.yml', 'r') as file:
        initial_prompt_dict = yaml.safe_load(file)
    with open(f'{FILES_PATH}/prompts/refine_prompt.yml', 'r') as file:
        refine_prompt_dict = yaml.safe_load(file)
    assert isinstance(initial_prompt_dict, dict)
    prompts = {
        'initial_prompt': initial_prompt_dict,
        'refine_prompt': refine_prompt_dict
    }
    task = RefineTextAnalysisTask(file_path=file_path, prompts=prompts)
    result = task.perform_task()
    assert 'input_documents' in result
    assert 'output_text' in result


def test_refine_text_analysis_fail():
    """Test refine text analysis task failure"""
    file_path = f'{FILES_PATH}/docs/test.txt'
    with pytest.raises(ValueError) as exc:
        RefineTextAnalysisTask(file_path=file_path)
    assert str(exc.value) == "Prompts dictionary must be provided."

    with pytest.raises(ValueError) as exc:
        RefineTextAnalysisTask(file_path=file_path, prompts={'initial_prompt': 'init'})
    assert str(exc.value) == "Missing required prompts: refine_prompt"

    prompts = {
        'initial_prompt': 'initial_prompt.yml',
        'refine_prompt': 'refine_prompt.yml'
    }
    file_path = f'{FILES_PATH}/docs/not.found'
    with pytest.raises(FileNotFoundError) as exc:
        an = RefineTextAnalysisTask(file_path=file_path, prompts=prompts)
        an.perform_task()
