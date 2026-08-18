"""Shared test helpers for the eval adapter test suite."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

from pydantic import BaseModel

from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.sandbox_worker import execute_scorer_bridged
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    SkippedReason,
    V2EvalResult,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.tools.sandbox_bridge import NestedToolServer, run_bridged_child


# ---------------------------------------------------------------------------
# Code-eval scorer execution
# ---------------------------------------------------------------------------
def run_scorer(code: str, inputs: dict, timeout: float) -> dict:
    """Run a scorer through the shared bridge and return its raw ``result`` message.

    Preserves the call shape of the single-queue ``sandbox_worker.run_scorer`` that
    the two-queue bridge replaced, so the worker's behavioural suite and its
    benchmarks did not have to be rewritten around an async, server-carrying API.
    Raises ``RuntimeError`` on timeout / crash, mirroring how ``CodeEvalAdapter``
    maps those outcomes.
    """
    return asyncio.run(_run_scorer_async(code, inputs, timeout))


async def _run_scorer_async(code: str, inputs: dict, timeout: float) -> dict:
    server = NestedToolServer(
        allowlist=[], project=Project(name="worker_test"), task=None, context=None
    )
    res = await run_bridged_child(
        target=execute_scorer_bridged,
        args=(code, inputs),
        timeout_s=float(timeout),
        server=server,
    )
    if res.timed_out:
        raise RuntimeError(f"Code eval scorer timed out after {timeout}s")
    if res.crashed:
        raise RuntimeError(f"Scorer crashed (exit code {res.exit_code})")
    assert res.result_msg is not None
    return res.result_msg


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
