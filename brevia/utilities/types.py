"""Utilities for handling types"""
from importlib import import_module


def load_type(name: str, parent_type: type | None = None, default_module:
              str | None = None) -> type:
    """
        Return a type from a string with a qualified or unqualified name.

        Args:
            name: The name of the class to load, can be a fully qualified name
                or an unqualified name.
            parent_type: The parent type that the class must extend.
                No check is performed if None is passed.
            default_module: The default module to use if the name is unqualified.
                Required if the name is unqualified.
    """
    if '.' not in name:  # unqualified name
        if not default_module:
            raise ValueError('default_module is needed for an unqualified name')
        name = f'{default_module}.{name}'
    module_name, class_name = name.rsplit('.', 1)
    try:
        module = import_module(module_name)
    except ModuleNotFoundError:
        raise ValueError(f'Module "{module_name}" not found')
    if not hasattr(module, class_name):
        raise ValueError(f'Class "{class_name}" not found in "{module_name}"')
    new_class = getattr(module, class_name)
    if parent_type and not issubclass(new_class, parent_type):
        raise ValueError(f'Class "{class_name}" must extend "{parent_type.__name__}"')

    return new_class
