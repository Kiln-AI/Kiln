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
    rag_judge_templates,
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
    "rag_judge_templates",
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
