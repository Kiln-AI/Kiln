"""Shared test helpers for the eval adapter test suite."""

from __future__ import annotations

from unittest.mock import Mock

from pydantic import BaseModel

from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    SkippedReason,
    V2EvalResult,
)


# ---------------------------------------------------------------------------
# Stub V2 adapters (test-only, never registered in prod)
# ---------------------------------------------------------------------------
class StubV2Eval(BaseV2EvalBridge):
    """Stub that returns a passing score."""

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        return V2EvalResult(scores={"accuracy": 1.0})


class SkippingStubV2Eval(BaseV2EvalBridge):
    """Stub that returns a skip."""

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        return V2EvalResult(
            skipped_reason=SkippedReason.extraction_failed,
            skipped_detail="test skip detail",
        )


# ---------------------------------------------------------------------------
# Config / input factory helpers for deterministic matcher tests
# ---------------------------------------------------------------------------
def make_v2_eval_config(
    props: BaseModel,
    output_scores: list[EvalOutputScore] | None = None,
) -> EvalConfig:
    """Build a mock V2 EvalConfig with the given properties.

    Used by deterministic matcher tests (exact_match, contains, pattern_match,
    set_check, tool_call_check, step_count_check) to replace the per-file
    ``_make_config`` boilerplate.
    """
    if output_scores is None:
        output_scores = [
            EvalOutputScore(
                name="score_a",
                instruction="a",
                type=TaskOutputRatingType.pass_fail,
            ),
        ]
    parent = Mock()
    parent.output_scores = output_scores
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    cfg.parent_eval.return_value = parent
    return cfg


def make_eval_task_input(
    final_message: str = "Hello world",
    **overrides: object,
) -> EvalTaskInput:
    """Build an ``EvalTaskInput`` with sensible defaults.

    Callers that need a different ``final_message`` default (e.g. set_check
    tests that use JSON lists) pass it explicitly.
    """
    defaults: dict = {
        "final_message": final_message,
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)
