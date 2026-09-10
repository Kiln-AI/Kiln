"""Tests for the kiln_ai.datamodel.usage back-compat shim.

The classes themselves live in ``kiln_ai.utils.usage`` (see that module for
the import cycle the split breaks) and are tested in ``utils/test_usage.py``.
What is left here is the shim's own contract: every historical import path
still resolves to the one real class, including inside old pickles.
"""

import pickle

import pytest

from kiln_ai.datamodel import MessageUsage as MessageUsageFromDatamodel
from kiln_ai.datamodel import Usage as UsageFromDatamodel
from kiln_ai.datamodel.task_run import MessageUsage as MessageUsageFromTaskRun
from kiln_ai.datamodel.task_run import Usage as UsageFromTaskRun
from kiln_ai.datamodel.usage import MessageUsage, Usage
from kiln_ai.utils.usage import MessageUsage as MessageUsageFromUtils
from kiln_ai.utils.usage import Usage as UsageFromUtils


def test_usage_re_exported_from_task_run():
    """`from kiln_ai.datamodel.task_run import Usage` returns the same class
    as `from kiln_ai.datamodel.usage import Usage`. Existing import sites
    must keep working after the file move."""
    assert UsageFromTaskRun is Usage


def test_usage_re_exported_from_datamodel_init():
    """`from kiln_ai.datamodel import Usage` continues to resolve to the
    moved class via the existing __init__.py re-export chain."""
    assert UsageFromDatamodel is Usage


def test_message_usage_re_exported_from_task_run():
    """`MessageUsage` mirrors the `Usage` re-export pattern."""
    assert MessageUsageFromTaskRun is MessageUsage


def test_message_usage_re_exported_from_datamodel_init():
    assert MessageUsageFromDatamodel is MessageUsage


def test_datamodel_usage_re_exports_the_utils_classes():
    """`kiln_ai.datamodel.usage` is a thin re-export of the real classes, so
    both import paths yield one class -- isinstance checks and pydantic
    validation can't diverge between callers."""
    assert Usage is UsageFromUtils
    assert MessageUsage is MessageUsageFromUtils


@pytest.mark.parametrize("model_class", [MessageUsage, Usage])
def test_usage_unpickles_from_the_legacy_module_path(model_class):
    """Pickles written before the move name `kiln_ai.datamodel.usage.<class>`.

    Protocol 0 writes the module path as plain newline-terminated text, so
    rewriting it here produces exactly what an older Kiln would have emitted.
    """
    original = model_class(input_tokens=3, cost=0.25)
    legacy_bytes = pickle.dumps(original, protocol=0).replace(
        b"kiln_ai.utils.usage", b"kiln_ai.datamodel.usage"
    )

    restored = pickle.loads(legacy_bytes)

    assert type(restored) is model_class
    assert restored == original
