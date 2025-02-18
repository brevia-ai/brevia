"""Services module tests"""
from pathlib import Path
import pytest
from brevia.services import (
    SummarizeFileService,
    SummarizeTextService,
    RefineTextAnalysisService,
)
from brevia.settings import get_settings


def test_summarize_failures():
    """Test summarize service classes failures"""
    service = SummarizeTextService()
    with pytest.raises(ValueError) as exc:
        service.run({})
    assert str(exc.value) == 'Invalid service payload - {}'

    service = SummarizeFileService()
    with pytest.raises(ValueError) as exc:
        service.run({})
    assert str(exc.value) == 'Invalid service payload - {}'

    folder_path = f'{Path(__file__).parent}/files'
    file_path = f'{folder_path}/empty-text.txt'
    Path(file_path).touch()
    with pytest.raises(ValueError) as exc:
        service.run({'file_path': file_path})
    assert str(exc.value) == 'Empty text'


def test_refine_text_analysis():
    """Test refine text analysis service"""
    files_path = f'{Path(__file__).parent}/files'
    settings = get_settings()
    current_path = settings.prompts_base_path
    settings.prompts_base_path = f'{files_path}/prompts'
    payload = {
        'file_path': f'{files_path}/docs/test.txt',
        'prompts': {
            'initial_prompt': 'initial_prompt.yml',
            'refine_prompt': 'refine_prompt.yml'
        }
    }
    service = RefineTextAnalysisService()
    result = service.run(payload)
    assert 'output' in result
    assert 'token_data' in result
    settings.prompts_base_path = current_path


def test_refine_text_analysis_fail():
    """Test refine text analysis service failure"""
    service = RefineTextAnalysisService()
    with pytest.raises(ValueError) as exc:
        service.run({})
    assert str(exc.value) == 'Invalid service payload - {}'

    with pytest.raises(ValueError) as exc:
        service.run({
            'file_path': '/some/path',
            'prompts': {'a': 'b'}
        })
    assert str(exc.value).startswith('Invalid service payload - ')
