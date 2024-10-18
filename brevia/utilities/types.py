"""Utilities for type checking and conversion."""
from importlib import import_module


def load_type(name: str, parent_type: type | None = None, default_module:
              str | None = None) -> type:
    """ Return a type from a string with a python module path """
    if '.' not in name:
        if not default_module:
            raise ValueError('default_module is needed for name without a module path')
        name = f'{default_module}.{name}'
    module_name, class_name = name.rsplit('.', 1)
    try:
        module = import_module(module_name)
    except ModuleNotFoundError:
        raise ValueError(f'Module "{module_name}" not found')
    if not hasattr(module, class_name):
        raise ValueError(f'Class "{class_name}" not found in "{module}"')
    new_class = getattr(module, class_name)
    if parent_type and not issubclass(new_class, parent_type):
        raise ValueError(f'Class "{class_name}" must extend "{parent_type}"')

    return new_class
