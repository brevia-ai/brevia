"""Test text analysis tasks"""
from pathlib import Path
import pytest
from brevia.tasks.text_analysis import RefineTextAnalysisTask
import yaml


def test_refine_text_analysis():
    """Test refine text analysis task"""
    file_path = f'{Path(__file__).parent.parent}/files/docs/test.txt'
    prompts = {
        'initial_prompt': 'initial_prompt.yml',
        'refine_prompt': 'refine_prompt.yml'
    }
    task = RefineTextAnalysisTask(file_path=file_path, prompts=prompts)
    result = task.perform_task()
    assert 'input_documents' in result
    assert 'output_text' in result
    with open(f'{Path(__file__).parent.parent}/files/prompts/initial_prompt.yml', 'r') as file:
        initial_prompt_dict = yaml.safe_load(file)
    with open(f'{Path(__file__).parent.parent}/files/prompts/refine_prompt.yml', 'r') as file:
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
    file_path = f'{Path(__file__).parent.parent}/files/docs/test.txt'
    with pytest.raises(ValueError) as exc:
        RefineTextAnalysisTask(file_path=file_path)
    assert str(exc.value) == "Both 'initial_prompt' and 'refine_prompt' must be provided."

    prompts = {
        'initial_prompt': 'initial_prompt.yml',
        'refine_prompt': 'refine_prompt.yml'
    }
    file_path = f'{Path(__file__).parent.parent}/files/docs/not.found'
    with pytest.raises(FileNotFoundError) as exc:
        an = RefineTextAnalysisTask(file_path=file_path, prompts=prompts)
        an.perform_task()
