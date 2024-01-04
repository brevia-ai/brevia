"""Services module tests"""
import pytest
from pathlib import Path
from brevia.services import SummarizeFileService, SummarizeTextService


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
