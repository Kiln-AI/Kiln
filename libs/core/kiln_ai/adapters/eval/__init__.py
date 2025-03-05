"""
# Evals

This module contains the code for evaluating the performance of a model.

The submodules contain:

- BaseEval: each eval technique implements this interface.
- G-Eval: an eval implementation, that implements G-Eval and LLM as Judge.
- EvalRunner: a class that runs an full evaluation (many smaller evals jobs). Includes async parallel processing, and the ability to restart where it left off.
- EvalRegistry: a registry for all eval implementations.

The datamodel for Evals is in the `kiln_ai.datamodel.eval` module.
"""

from . import (
    base_eval,
    eval_runner,
    g_eval,
    registry,
)

__all__ = [
    "base_eval",
    "eval_runner",
    "g_eval",
    "registry",
]
