"""run_service module tests"""
import pytest
from brevia.utilities.run_service import run_service_from_yaml


def test_run_service_from_yaml():
    """Test run_service_from_yaml failure"""
    with pytest.raises(FileNotFoundError) as exc:
        run_service_from_yaml(file_path='/not/existent')
    assert str(exc.value) == '/not/existent'
