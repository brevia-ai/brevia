"""brevia.utilities.types module tests"""
from pydantic_settings import BaseSettings
import pytest
from brevia.utilities.types import load_type
from brevia.settings import Settings


def test_load_type():
    """Test load_type"""
    cls = load_type(name='brevia.settings.Settings')
    assert cls == Settings
    cls = load_type(name='Settings', default_module='brevia.settings')
    assert cls == Settings
    cls = load_type(name='Settings', default_module='brevia.settings',
                    parent_type=BaseSettings)
    assert cls == Settings


def test_load_type_failure():
    """Test load_type failure cases"""
    with pytest.raises(ValueError) as exc:
        load_type('NonExistent')
    assert str(exc.value) == 'default_module is needed for an unqualified name'

    with pytest.raises(ValueError) as exc:
        load_type('nonexisting.module.NonExistent')
    assert str(exc.value) == 'Module "nonexisting.module" not found'

    with pytest.raises(ValueError) as exc:
        load_type('brevia.utilities.types.NonExistent')
    assert str(exc.value) == 'Class "NonExistent" not found in "brevia.utilities.types"'

    with pytest.raises(ValueError) as exc:
        load_type(name='brevia.settings.Settings', parent_type=ValueError)
    assert str(exc.value) == 'Class "Settings" must extend "ValueError"'
