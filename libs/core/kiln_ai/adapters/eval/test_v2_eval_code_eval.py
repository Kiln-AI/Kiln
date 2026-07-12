"""Tests for CodeEvalAdapter and trust gate helpers."""

import asyncio
import threading
import time
from unittest.mock import Mock, PropertyMock, patch

import pytest

from kiln_ai.adapters.eval.v2_eval_code_eval import (
    CodeEvalAdapter,
    _trusted_projects,
    grant_code_eval_trust,
    is_code_eval_trusted,
    revoke_code_eval_trust,
)
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    SkippedReason,
)


@pytest.fixture(autouse=True)
def _clear_trust():
    _trusted_projects.clear()
    yield
    _trusted_projects.clear()


def _make_config(
    code: str = "def score(output, trace, reference_data, task_input):\n    return {'accuracy': 1.0}\n",
    timeout: int = 30,
) -> EvalConfig:
    props = CodeEvalProperties(code=code, timeout_seconds=timeout)
    parent_eval = Mock()
    parent_eval.output_scores = [
        EvalOutputScore(
            name="accuracy",
            instruction="Rate accuracy",
            type=TaskOutputRatingType.five_star,
        ),
    ]
    parent_task = Mock()
    parent_project = Mock()
    parent_project.id = "project-123"
    parent_project.path = "/fake/project/path"
    parent_task.parent = parent_project
    parent_eval.parent_task.return_value = parent_task

    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    cfg.parent_eval.return_value = parent_eval
    return cfg


def _inp(**overrides) -> EvalTaskInput:
    defaults: dict = {
        "final_message": "Hello world",
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)


class TestTrustGate:
    def test_grant_and_check(self):
        assert not is_code_eval_trusted("proj-1")
        grant_code_eval_trust("proj-1")
        assert is_code_eval_trusted("proj-1")

    def test_revoke(self):
        grant_code_eval_trust("proj-1")
        revoke_code_eval_trust("proj-1")
        assert not is_code_eval_trusted("proj-1")

    def test_revoke_nonexistent_is_noop(self):
        revoke_code_eval_trust("proj-never-added")

    def test_multiple_projects(self):
        grant_code_eval_trust("proj-a")
        grant_code_eval_trust("proj-b")
        assert is_code_eval_trusted("proj-a")
        assert is_code_eval_trusted("proj-b")
        revoke_code_eval_trust("proj-a")
        assert not is_code_eval_trusted("proj-a")
        assert is_code_eval_trusted("proj-b")


class TestCodeEvalAdapterInit:
    def test_valid_construction(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        assert adapter.properties is cfg.properties

    def test_non_code_eval_properties_raises(self):
        cfg = Mock(spec=EvalConfig)
        cfg.config_type = EvalConfigType.v2
        cfg.properties = Mock()
        with pytest.raises(ValueError):
            CodeEvalAdapter(cfg)


class TestCodeEvalAdapterEvaluate:
    @pytest.mark.asyncio
    async def test_untrusted_project_skips(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp())
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.code_eval_not_trusted
        assert result.skipped_detail is not None

    @pytest.mark.asyncio
    async def test_successful_evaluation(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": {"accuracy": 0.95}}
            result = await adapter.evaluate(_inp())

        assert result.scores == {"accuracy": 0.95}
        assert result.skipped_reason is None
        assert result.skipped_detail is None

    @pytest.mark.asyncio
    async def test_timeout_raises_runtime_error(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.side_effect = RuntimeError("Code eval scorer timed out after 30s")
            with pytest.raises(RuntimeError, match="timed out"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_scorer_error_raises_runtime_error(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {
                "error": "NameError: undefined",
                "traceback": "Traceback...",
            }
            with pytest.raises(RuntimeError, match="Code eval scorer failed"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_non_dict_result_raises(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": "not a dict"}
            with pytest.raises(RuntimeError, match="Scorer must return a dict"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_inputs_passed_correctly(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": {"accuracy": 1.0}}
            await adapter.evaluate(
                _inp(
                    final_message="test output",
                    trace=[{"role": "user", "content": "some trace"}],
                    reference_data={"key": "ref"},
                    task_input="input data",
                )
            )

        call_args = mock_run.call_args
        inputs = call_args[0][1]
        assert inputs["output"] == "test output"
        assert inputs["trace"] == [{"role": "user", "content": "some trace"}]
        assert inputs["reference_data"] == {"key": "ref"}
        assert inputs["task_input"] == "input data"


class TestScoreValidation:
    @pytest.mark.asyncio
    async def test_bool_rejected(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": {"accuracy": True}}
            with pytest.raises(RuntimeError, match="returned a bool"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_int_converted_to_float(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": {"accuracy": 1}}
            result = await adapter.evaluate(_inp())

        assert result.scores == {"accuracy": 1.0}
        assert isinstance(result.scores["accuracy"], float)
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_key_mismatch_raises(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": {"wrong_key": 0.5}}
            with pytest.raises(RuntimeError, match="Score key mismatch"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_string_score_rejected(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": {"accuracy": "high"}}
            with pytest.raises(RuntimeError, match="must be a float"):
                await adapter.evaluate(_inp())

    def test_no_parent_eval_raises(self):
        cfg = _make_config()
        cfg.parent_eval.return_value = None
        with pytest.raises(ValueError, match="parent eval"):
            CodeEvalAdapter(cfg)


class TestAsyncScorerEndToEnd:
    @pytest.mark.asyncio
    async def test_async_scorer_returns_validated_scores(self):
        code = (
            "async def score(output, trace, reference_data, task_input):\n"
            "    return {'accuracy': 0.75}\n"
        )
        cfg = _make_config(code=code)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        result = await adapter.evaluate(_inp(final_message="test"))
        assert result.scores == {"accuracy": 0.75}
        assert result.skipped_reason is None
        assert result.skipped_detail is None


class TestResolveProjectPath:
    def test_no_project_returns_none(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        adapter.target_task.parent = None
        assert adapter._resolve_project_path() is None

    def test_no_path_returns_none(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        adapter.target_task.parent.path = None
        assert adapter._resolve_project_path() is None

    def test_valid_chain_returns_path(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        assert adapter._resolve_project_path() == "/fake/project/path"

    def test_exception_returns_none(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        broken_parent = PropertyMock(side_effect=RuntimeError("broken"))
        type(adapter.target_task).parent = broken_parent
        assert adapter._resolve_project_path() is None


class TestExecutionSerialization:
    @pytest.mark.asyncio
    async def test_concurrent_evaluations_are_serialized(self):
        """Two concurrent evaluate() calls must not overlap execution.

        run_scorer is called inside run_in_executor (a thread pool thread).
        We replace it with a slow mock that tracks concurrency via a
        threading counter. If the asyncio.Lock serialization works, the
        counter never exceeds 1.
        """
        cfg1 = _make_config()
        cfg2 = _make_config()
        adapter1 = CodeEvalAdapter(cfg1)
        adapter2 = CodeEvalAdapter(cfg2)
        grant_code_eval_trust("/fake/project/path")

        counter_lock = threading.Lock()
        concurrency_counter = 0
        max_concurrency = 0

        def slow_run_scorer(code, inputs, timeout):
            nonlocal concurrency_counter, max_concurrency
            with counter_lock:
                concurrency_counter += 1
                max_concurrency = max(max_concurrency, concurrency_counter)
            time.sleep(0.05)
            with counter_lock:
                concurrency_counter -= 1
            return {"ok": {"accuracy": 1.0}}

        with patch(
            "kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer",
            side_effect=slow_run_scorer,
        ):
            await asyncio.gather(
                adapter1.evaluate(_inp()),
                adapter2.evaluate(_inp()),
            )

        assert max_concurrency == 1, (
            f"Expected serialized execution (max concurrency 1), got {max_concurrency}"
        )


class TestFiniteScoreValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    async def test_non_finite_rejected(self, bad):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        with patch("kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer") as mock_run:
            mock_run.return_value = {"ok": {"accuracy": bad}}
            with pytest.raises(RuntimeError, match="finite"):
                await adapter.evaluate(_inp())


class TestUsageObjectTransport:
    @pytest.mark.asyncio
    async def test_message_usage_objects_survive_to_scorer(self):
        """Live-path traces carry Pydantic MessageUsage OBJECTS (pickle
        transport), not dicts — a scorer using get_usage_totals must work
        end-to-end through the real sandbox."""
        from kiln_ai.datamodel.usage import MessageUsage

        code = (
            "from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers as H\n"
            "def score(trace):\n"
            "    return {'accuracy': min(H.get_usage_totals(trace)['total_tokens'], 5.0)}\n"
        )
        cfg = _make_config(code=code)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust("/fake/project/path")

        trace = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "reply",
                "latency_ms": 100,
                "usage": MessageUsage(
                    input_tokens=100, output_tokens=50, total_tokens=150
                ),
            },
        ]
        result = await adapter.evaluate(_inp(trace=trace))
        assert result.scores == {"accuracy": 5.0}
