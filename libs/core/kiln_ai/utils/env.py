import os
from contextlib import contextmanager


@contextmanager
def temporary_env(var_name: str, value: str):
    old_value = os.environ.get(var_name)
    os.environ[var_name] = value
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop(var_name, None)  # remove if it did not exist before
        else:
            os.environ[var_name] = old_value
