"""Packaging checks: the installed distribution is importable and typed."""

import importlib
import inspect
from importlib.resources import files

import pytest

import brevia

pytestmark = pytest.mark.unit


def test_version_matches_the_distribution_metadata() -> None:
    assert brevia.__version__ == "1.0.0b1"


def test_package_declares_inline_types() -> None:
    assert files("brevia").joinpath("py.typed").is_file()


PUBLIC_MODULES = ("brevia.analysis", "brevia.tools", "brevia.api", "brevia.testing")
"""Documented modules whose ``__all__`` is part of the public API."""


@pytest.mark.parametrize("module_name", ["brevia", *PUBLIC_MODULES])
def test_public_api_exports_only_brevia_objects(module_name: str) -> None:
    module = importlib.import_module(module_name)
    for name in module.__all__:
        value = getattr(module, name)
        if not (isinstance(value, type) or inspect.isfunction(value)):
            continue  # constants and type aliases
        origin = value.__module__
        # Pydantic AI and other dependencies must not leak into the public API.
        assert origin.startswith("brevia"), (name, origin)
