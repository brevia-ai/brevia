"""Test text analysis tasks"""
from pathlib import Path
import pytest
from brevia.settings import get_settings
from brevia.tasks.text_analysis import RefineTextAnalysisTask
import yaml

FILES_PATH = f'{Path(__file__).parent.parent}/files'


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
