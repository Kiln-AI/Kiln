"""
# Evals

This module contains the code for evaluating the performance of a model.

The submodules contain:

- BaseEval: each eval technique implements this interface.
- G-Eval: an eval implementation, that implements G-Eval and LLM as Judge.
- EvalRunner: a class that runs an full evaluation (many smaller evals jobs). Includes async parallel processing, and the ability to restart where it left off.
- EvalRegistry: a registry for all eval implementations.

The datamodel for Evals is in the `kiln_ai.datamodel.eval` module.

Submodules are loaded lazily via PEP 562 __getattr__ so that importing
``kiln_ai.adapters.eval`` does not eagerly pull in every eval adapter and
its transitive dependencies.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import (
        base_eval,
        eval_runner,
        g_eval,
        registry,
        v2_eval_code_eval,
        v2_eval_contains,
        v2_eval_exact_match,
        v2_eval_llm_judge,
        v2_eval_pattern_match,
        v2_eval_set_check,
        v2_eval_step_count_check,
        v2_eval_tool_call_check,
    )

__all__ = [
    "base_eval",
    "eval_runner",
    "g_eval",
    "registry",
    "v2_eval_code_eval",
    "v2_eval_contains",
    "v2_eval_exact_match",
    "v2_eval_llm_judge",
    "v2_eval_pattern_match",
    "v2_eval_set_check",
    "v2_eval_step_count_check",
    "v2_eval_tool_call_check",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return __all__
