"""Services module tests"""
from pathlib import Path
import pytest
from brevia.services import (
    SummarizeFileService,
    SummarizeTextService,
    RefineTextAnalysisService,
)


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
    payload = {
        'file_path': f'{Path(__file__).parent}/files/docs/test.txt',
        'prompts': {
            'initial_prompt': 'initial_prompt.yml',
            'refine_prompt': 'refine_prompt.yml'
        }
    }
    service = RefineTextAnalysisService()
    result = service.run(payload)
    assert 'output' in result
    assert 'token_data' in result
