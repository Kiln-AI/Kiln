"""Tests for V2 dispatch scaffolding, BaseV2EvalBridge contract, and extraction helpers."""

from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    check_reference_key,
    check_required_vars,
    extract_value,
)
from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.adapters.eval.registry import (
    _V2_ADAPTER_MAP,
    eval_adapter_from_type,
    v2_eval_adapter_from_config,
)
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    ContainsProperties,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalScores,
    EvalTaskInput,
    ExactMatchProperties,
    LlmJudgeProperties,
    PatternMatchProperties,
    SetCheckProperties,
    SkippedReason,
    StepCountCheckProperties,
    ToolCallCheckProperties,
    V2EvalType,
)


# ---------------------------------------------------------------------------
# Stub V2 adapter (test-only, never registered in prod)
# ---------------------------------------------------------------------------
class StubV2Eval(BaseV2EvalBridge):
    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        return {"stub_score": 1.0}, None, None


class SkippingStubV2Eval(BaseV2EvalBridge):
    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        return {}, SkippedReason.extraction_failed, "test skip"


# ---------------------------------------------------------------------------
# Helpers for building mock configs
# ---------------------------------------------------------------------------
def _props_for_type(v2_type: V2EvalType):  # type: ignore[no-untyped-def]
    """Return minimal valid properties for a given V2EvalType."""
    match v2_type:
        case V2EvalType.exact_match:
            return ExactMatchProperties(expected_value="test")
        case V2EvalType.pattern_match:
            return PatternMatchProperties(pattern=".*")
        case V2EvalType.contains:
            return ContainsProperties(substring="test")
        case V2EvalType.set_check:
            return SetCheckProperties(expected_set=["a"], mode="equal")
        case V2EvalType.tool_call_check:
            return ToolCallCheckProperties(expected_tools=[])
        case V2EvalType.step_count_check:
            return StepCountCheckProperties(count_type="turns", min_count=1)
        case V2EvalType.llm_judge:
            return LlmJudgeProperties(
                model_name="gpt-4o",
                model_provider="openai",
                prompt_template="test template",
            )
        case V2EvalType.code_eval:
            return CodeEvalProperties(
                code="def score(output, trace, reference_data, task_input, kiln):\n    return {'score': 1.0}\n"
            )
        case _:
            return ExactMatchProperties(expected_value="test")


def _mock_v2_eval_config(v2_type: V2EvalType = V2EvalType.exact_match) -> EvalConfig:
    props = _props_for_type(v2_type)
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    cfg.parent_eval.return_value = Mock(
        output_scores=[
            EvalOutputScore(
                name="score",
                instruction="s",
                type=TaskOutputRatingType.pass_fail,
            )
        ]
    )
    return cfg


def _sample_eval_input(**overrides) -> EvalTaskInput:  # type: ignore[no-untyped-def]
    defaults: dict = {
        "final_message": "Hello world",
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)


# ===================================================================
# BaseV2EvalBridge contract tests
# ===================================================================
class TestBaseV2EvalBridgeContract:
    def test_abstract_contract(self):
        import inspect

        assert inspect.isabstract(BaseV2EvalBridge) is False
        assert hasattr(BaseV2EvalBridge.evaluate, "__isabstractmethod__")
        assert BaseV2EvalBridge.evaluate.__isabstractmethod__ is True

    @pytest.mark.asyncio
    async def test_stub_evaluate(self):
        cfg = _mock_v2_eval_config()
        adapter = StubV2Eval(cfg)
        scores, skip, detail = await adapter.evaluate(_sample_eval_input())
        assert scores == {"stub_score": 1.0}
        assert skip is None
        assert detail is None

    @pytest.mark.asyncio
    async def test_stub_receives_eval_task_input(self):
        cfg = _mock_v2_eval_config()
        adapter = StubV2Eval(cfg)
        inp = _sample_eval_input(
            final_message="test msg",
            trace=[{"role": "user", "content": "hi"}],
            reference_data={"key": "val"},
            task_input="some input",
        )
        scores, skip, _detail = await adapter.evaluate(inp)
        assert scores == {"stub_score": 1.0}
        assert skip is None

    def test_rejects_non_v2_config(self):
        cfg = Mock(spec=EvalConfig)
        cfg.config_type = EvalConfigType.g_eval
        cfg.properties = ExactMatchProperties(expected_value="test")
        with pytest.raises(ValueError, match="V2 eval requires a V2 config_type"):
            StubV2Eval(cfg)

    def test_rejects_non_basemodel_properties(self):
        cfg = Mock(spec=EvalConfig)
        cfg.config_type = EvalConfigType.v2
        cfg.properties = {"type": "exact_match"}
        with pytest.raises(ValueError, match="V2 eval requires typed V2 properties"):
            StubV2Eval(cfg)

    @pytest.mark.asyncio
    async def test_skipping_stub_returns_skip(self):
        cfg = _mock_v2_eval_config()
        adapter = SkippingStubV2Eval(cfg)
        scores, skip, detail = await adapter.evaluate(_sample_eval_input())
        assert scores == {}
        assert skip == SkippedReason.extraction_failed
        assert detail == "test skip"


# ===================================================================
# Dispatch tests
# ===================================================================
class TestV2Dispatch:
    def test_dispatch_all_registered_types(self):
        from kiln_ai.adapters.eval.v2_eval_code_eval import CodeEvalAdapter
        from kiln_ai.adapters.eval.v2_eval_contains import ContainsEval
        from kiln_ai.adapters.eval.v2_eval_exact_match import ExactMatchEval
        from kiln_ai.adapters.eval.v2_eval_llm_judge import LlmJudgeEval
        from kiln_ai.adapters.eval.v2_eval_pattern_match import PatternMatchEval
        from kiln_ai.adapters.eval.v2_eval_set_check import SetCheckEval
        from kiln_ai.adapters.eval.v2_eval_step_count_check import StepCountCheckEval
        from kiln_ai.adapters.eval.v2_eval_tool_call_check import ToolCallCheckEval

        expected_map: dict[V2EvalType, type[BaseV2EvalBridge]] = {
            V2EvalType.exact_match: ExactMatchEval,
            V2EvalType.pattern_match: PatternMatchEval,
            V2EvalType.contains: ContainsEval,
            V2EvalType.set_check: SetCheckEval,
            V2EvalType.tool_call_check: ToolCallCheckEval,
            V2EvalType.step_count_check: StepCountCheckEval,
            V2EvalType.llm_judge: LlmJudgeEval,
            V2EvalType.code_eval: CodeEvalAdapter,
        }
        for v2_type, expected_cls in expected_map.items():
            cfg = _mock_v2_eval_config(v2_type)
            adapter = v2_eval_adapter_from_config(cfg)
            assert isinstance(adapter, expected_cls), (
                f"Expected {expected_cls.__name__} for {v2_type}, got {type(adapter).__name__}"
            )

    def test_with_monkeypatched_stub(self, monkeypatch):
        monkeypatch.setitem(_V2_ADAPTER_MAP, V2EvalType.exact_match, StubV2Eval)
        cfg = _mock_v2_eval_config(V2EvalType.exact_match)
        adapter = v2_eval_adapter_from_config(cfg)
        assert isinstance(adapter, StubV2Eval)

    def test_rejects_legacy_config(self):
        cfg = Mock(spec=EvalConfig)
        cfg.config_type = EvalConfigType.g_eval
        with pytest.raises(ValueError, match="only accepts V2 configs"):
            v2_eval_adapter_from_config(cfg)

    def test_legacy_dispatch_unchanged(self):
        for ct in (EvalConfigType.g_eval, EvalConfigType.llm_as_judge):
            cfg = Mock(spec=EvalConfig)
            cfg.config_type = ct
            assert eval_adapter_from_type(cfg) is GEval


# ===================================================================
# Extraction helper tests
# ===================================================================
class TestExtractValue:
    def test_from_final_message(self):
        inp = _sample_eval_input(final_message="the output")
        value, skip, detail = extract_value(None, inp)
        assert value == "the output"
        assert skip is None
        assert detail is None

    def test_from_expression(self):
        inp = _sample_eval_input(
            trace=[{"content": "traced"}],
        )
        value, skip, _detail = extract_value("trace[0].content", inp)
        assert value == "traced"
        assert skip is None

    def test_undefined_skips(self):
        inp = _sample_eval_input()
        value, skip, detail = extract_value("nonexistent_field", inp)
        assert value is None
        assert skip == SkippedReason.extraction_failed
        assert detail is not None and "undefined" in detail.lower()


class TestCheckReferenceKey:
    def test_key_present(self):
        inp = _sample_eval_input(reference_data={"answer": "42"})
        value, skip, _detail = check_reference_key("answer", inp)
        assert value == "42"
        assert skip is None

    def test_key_missing(self):
        inp = _sample_eval_input(reference_data={"other": "val"})
        value, skip, _detail = check_reference_key("answer", inp)
        assert value is None
        assert skip == SkippedReason.missing_reference_key

    def test_no_reference_data(self):
        inp = _sample_eval_input(reference_data=None)
        value, skip, _detail = check_reference_key("answer", inp)
        assert value is None
        assert skip == SkippedReason.missing_reference_key


class TestCheckRequiredVars:
    def test_all_present(self):
        inp = _sample_eval_input(
            trace=[{"role": "user"}],
            reference_data={"key": "val"},
        )
        skip, detail = check_required_vars(["trace[0].role", "reference_data.key"], inp)
        assert skip is None
        assert detail is None

    def test_missing(self):
        inp = _sample_eval_input()
        skip, detail = check_required_vars(["nonexistent_var"], inp)
        assert skip == SkippedReason.extraction_failed
        assert detail is not None and "nonexistent_var" in detail
