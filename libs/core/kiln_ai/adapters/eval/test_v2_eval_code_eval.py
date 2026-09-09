"""Tests for CodeEvalAdapter and trust gate helpers."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.adapters.eval.v2_eval_code_eval import (
    CodeEvalAdapter,
    _reset_add_code_trust,
    add_code_trust,
    has_add_code_trust,
)
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
)
from kiln_ai.datamodel.task_output import TaskOutput
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.tools.sandbox_bridge import BridgeResult

_BRIDGE_PATH = "kiln_ai.adapters.eval.v2_eval_code_eval.run_bridged_child"


@pytest.fixture(autouse=True)
def _clear_trust():
    _reset_add_code_trust()
    yield
    _reset_add_code_trust()


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
    def test_add_and_check(self):
        assert not has_add_code_trust("proj-1")
        add_code_trust("proj-1")
        assert has_add_code_trust("proj-1")

    def test_add_is_idempotent(self):
        add_code_trust("proj-1")
        add_code_trust("proj-1")
        assert has_add_code_trust("proj-1")

    def test_reset_clears_all(self):
        add_code_trust("proj-a")
        add_code_trust("proj-b")
        _reset_add_code_trust()
        assert not has_add_code_trust("proj-a")
        assert not has_add_code_trust("proj-b")

    def test_multiple_projects(self):
        add_code_trust("proj-a")
        add_code_trust("proj-b")
        assert has_add_code_trust("proj-a")
        assert has_add_code_trust("proj-b")
        assert not has_add_code_trust("proj-c")


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
    async def test_successful_evaluation(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)

        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": {"accuracy": 0.95}}
            )
            result = await adapter.evaluate(_inp())

        assert result.scores == {"accuracy": 0.95}
        assert result.skipped_reason is None
        assert result.skipped_detail is None

    @pytest.mark.asyncio
    async def test_timeout_raises_runtime_error(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(timed_out=True)
            with pytest.raises(RuntimeError, match="timed out"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_crash_raises_runtime_error(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(crashed=True, exit_code=7)
            with pytest.raises(RuntimeError, match="exit code 7"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exit_code", [0, None])
    async def test_clean_exit_without_result_is_not_reported_as_a_crash(
        self, exit_code
    ):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(crashed=True, exit_code=exit_code)
            with pytest.raises(RuntimeError, match="exited without returning results"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_scorer_error_raises_runtime_error(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={
                    "type": "result",
                    "error": "NameError: undefined",
                    "traceback": "Traceback...",
                }
            )
            with pytest.raises(RuntimeError, match="Code eval scorer failed"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_non_dict_result_raises(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": "not a dict"}
            )
            with pytest.raises(RuntimeError, match="Scorer must return a dict"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_inputs_passed_correctly(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": {"accuracy": 1.0}}
            )
            await adapter.evaluate(
                _inp(
                    final_message="test output",
                    trace=[{"role": "user", "content": "some trace"}],
                    reference_data={"key": "ref"},
                    task_input="input data",
                )
            )

        inputs = mock_run.call_args.kwargs["args"][1]
        assert inputs["output"] == "test output"
        assert inputs["trace"] == [{"role": "user", "content": "some trace"}]
        assert inputs["reference_data"] == {"key": "ref"}
        assert inputs["task_input"] == "input data"


class TestScorerNamespace:
    """What the sandboxed `score(...)` call actually receives."""

    async def _namespace_for(self, eval_input: EvalTaskInput) -> dict:
        adapter = CodeEvalAdapter(_make_config())
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": {"accuracy": 1.0}}
            )
            await adapter.evaluate(eval_input)
        _code, inputs = mock_run.call_args.kwargs["args"]
        return inputs

    @pytest.mark.asyncio
    async def test_a_dataset_item_supplies_reference_answer(self):
        """A TaskRun-backed dataset item's stored output reaches user scorer code as
        `reference_data["reference_answer"]`. Scorers written against the older
        contract - where this was always None for a TaskRun dataset - now take the
        other branch, so the documented contract has to match this."""
        item = TaskRun(
            input="Who wrote Dune?", output=TaskOutput(output="Frank Herbert.")
        )
        trace = TaskRun(input="Who wrote Dune?", output=TaskOutput(output="Herbert."))

        inputs = await self._namespace_for(EvalTaskInput.from_trace(trace, item))

        assert inputs["reference_data"] == {"reference_answer": "Frank Herbert."}
        assert inputs["output"] == "Herbert."
        assert inputs["task_input"] == "Who wrote Dune?"

    @pytest.mark.asyncio
    async def test_calibration_supplies_no_reference_data(self):
        """A TaskRun scored as itself has no separate ground truth to hand the scorer."""
        golden = TaskRun(
            input="Who wrote Dune?", output=TaskOutput(output="Frank Herbert.")
        )

        inputs = await self._namespace_for(EvalTaskInput.from_task_run(golden))

        assert inputs["reference_data"] is None


class TestScoreValidation:
    @pytest.mark.asyncio
    async def test_bool_rejected(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": {"accuracy": True}}
            )
            with pytest.raises(RuntimeError, match="returned a bool"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_int_converted_to_float(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": {"accuracy": 1}}
            )
            result = await adapter.evaluate(_inp())

        assert result.scores == {"accuracy": 1.0}
        assert isinstance(result.scores["accuracy"], float)
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_key_mismatch_raises(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": {"wrong_key": 0.5}}
            )
            with pytest.raises(RuntimeError, match="Score key mismatch"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    async def test_string_score_rejected(self):
        cfg = _make_config()
        adapter = CodeEvalAdapter(cfg)
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BridgeResult(
                result_msg={"type": "result", "ok": {"accuracy": "high"}}
            )
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
        result = await adapter.evaluate(_inp(final_message="test"))
        assert result.scores == {"accuracy": 0.75}
        assert result.skipped_reason is None
        assert result.skipped_detail is None


# ---------------------------------------------------------------------------
# Synthetic world instances
# ---------------------------------------------------------------------------


class TestSyntheticInstanceHandoff:
    def _ctx(self, tmp_path, state_unavailable=False):
        from kiln_ai.datamodel.synthetic_world import SyntheticInstance
        from kiln_ai.run_context import SyntheticInstanceContext

        instance = SyntheticInstance(
            instance_id="inst_x",
            world_id="w",
            fixture_id="f",
            path=str(tmp_path / "inst"),
            fixture_data_path=str(tmp_path / "fixture"),
        )
        return SyntheticInstanceContext(
            instance=instance, world=Mock(), state_unavailable=state_unavailable
        )

    def test_scorer_declares(self):
        declares = CodeEvalAdapter._scorer_declares
        assert declares(
            "def score(output, synthetic_instance):\n    pass\n", "synthetic_instance"
        )
        assert declares(
            "def score(output, *, synthetic_instance=None):\n    pass\n",
            "synthetic_instance",
        )
        assert not declares("def score(output):\n    pass\n", "synthetic_instance")
        assert not declares(
            "def other(synthetic_instance):\n    pass\n", "synthetic_instance"
        )
        assert not declares("def score(:\n", "synthetic_instance")

    async def test_scorer_receives_full_record_and_context(self, tmp_path):
        from kiln_ai.run_context import reset_synthetic_instance, set_synthetic_instance

        cfg = _make_config(
            code="def score(output, synthetic_instance):\n    return {'accuracy': 1.0}\n"
        )
        adapter = CodeEvalAdapter(cfg)
        ctx = self._ctx(tmp_path)
        token = set_synthetic_instance(ctx)
        try:
            with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_bridge:
                mock_bridge.return_value = BridgeResult(
                    result_msg={"ok": {"accuracy": 1.0}}
                )
                await adapter.evaluate(_inp())
        finally:
            reset_synthetic_instance(token)
        _, kwargs = mock_bridge.call_args
        inputs = kwargs["args"][1]
        assert inputs["synthetic_instance"]["instance_id"] == "inst_x"
        assert inputs["synthetic_instance"]["path"] == str(tmp_path / "inst")
        assert kwargs["server"]._context.synthetic_instance is ctx.instance

    async def test_no_context_passes_none(self):
        adapter = CodeEvalAdapter(_make_config())
        with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = BridgeResult(
                result_msg={"ok": {"accuracy": 1.0}}
            )
            await adapter.evaluate(_inp())
        _, kwargs = mock_bridge.call_args
        assert kwargs["args"][1]["synthetic_instance"] is None
        assert kwargs["server"]._context.synthetic_instance is None

    async def test_evicted_state_skips_scorer_that_reads_it(self, tmp_path):
        from kiln_ai.datamodel.eval import SkippedReason
        from kiln_ai.run_context import reset_synthetic_instance, set_synthetic_instance

        cfg = _make_config(
            code="def score(output, synthetic_instance):\n    return {'accuracy': 1.0}\n"
        )
        adapter = CodeEvalAdapter(cfg)
        token = set_synthetic_instance(self._ctx(tmp_path, state_unavailable=True))
        try:
            with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_bridge:
                result = await adapter.evaluate(_inp())
        finally:
            reset_synthetic_instance(token)
        assert result.skipped_reason == SkippedReason.synthetic_instance_unavailable
        assert "inst_x" in (result.skipped_detail or "")
        mock_bridge.assert_not_called()

    async def test_evicted_state_still_runs_trace_only_scorer(self, tmp_path):
        from kiln_ai.run_context import reset_synthetic_instance, set_synthetic_instance

        adapter = CodeEvalAdapter(_make_config())
        token = set_synthetic_instance(self._ctx(tmp_path, state_unavailable=True))
        try:
            with patch(_BRIDGE_PATH, new_callable=AsyncMock) as mock_bridge:
                mock_bridge.return_value = BridgeResult(
                    result_msg={"ok": {"accuracy": 1.0}}
                )
                result = await adapter.evaluate(_inp())
        finally:
            reset_synthetic_instance(token)
        assert result.scores == {"accuracy": 1.0}

    def test_worker_passes_synthetic_instance_only_when_declared(self, tmp_path):
        from kiln_ai.adapters.eval.conftest import run_scorer

        record = {
            "instance_id": "inst_w",
            "world_id": "w",
            "fixture_id": "f",
            "path": str(tmp_path),
            "fixture_data_path": str(tmp_path),
            "frozen_time": "2026-07-14T00:00:00+00:00",
            "world_lib_path": None,
        }
        declared = (
            "import os\n"
            "def score(output, synthetic_instance):\n"
            "    return {'id': synthetic_instance['instance_id'],"
            " 'env': os.environ.get('KILN_SYNTHETIC_INSTANCE_ID')}\n"
        )
        msg = run_scorer(
            declared,
            {"output": "o", "task_input": None, "synthetic_instance": record},
            10,
        )
        assert msg["ok"] == {"id": "inst_w", "env": "inst_w"}

        undeclared = "def score(output):\n    return {'ok': 1}\n"
        msg = run_scorer(
            undeclared,
            {"output": "o", "task_input": None, "synthetic_instance": record},
            10,
        )
        assert msg["ok"] == {"ok": 1}
