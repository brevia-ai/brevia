"""Utilities for type checking and conversion."""
from importlib import import_module


def load_type(name: str, parent_type: type | None = None) -> type:
    """ Return a type from a string with a python module path """
    module_name, class_name = name.rsplit('.', 1)
    module = import_module(module_name)
    if not hasattr(module, class_name):
        raise ValueError(f'Class "{class_name}" not found in "{module}"')
    new_class = getattr(module, class_name)
    if parent_type and not issubclass(new_class, parent_type):
        raise ValueError(f'Class "{class_name}" must extend "{parent_type}"')

    return new_class
