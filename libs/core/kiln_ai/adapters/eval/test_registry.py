from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.adapters.eval.registry import (
    eval_adapter_from_type,
    v2_eval_adapter_from_config,
)
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    ContainsProperties,
    EvalConfig,
    EvalConfigType,
    ExactMatchProperties,
    LlmJudgeProperties,
    PatternMatchProperties,
    SetCheckProperties,
    StepCountCheckProperties,
    ToolCallCheckProperties,
    ToolCallSpec,
    V2EvalType,
)

_V2_TYPE_TO_PROPS = {
    V2EvalType.llm_judge: LlmJudgeProperties(
        model_name="m",
        model_provider="p",
        prompt_template="{{ final_message }}",
    ),
    V2EvalType.exact_match: ExactMatchProperties(expected_value="test"),
    V2EvalType.pattern_match: PatternMatchProperties(pattern=".*"),
    V2EvalType.contains: ContainsProperties(substring="test"),
    V2EvalType.set_check: SetCheckProperties(expected_set=["a"]),
    V2EvalType.tool_call_check: ToolCallCheckProperties(
        expected_tools=[ToolCallSpec(tool_name="t")],
    ),
    V2EvalType.step_count_check: StepCountCheckProperties(
        count_type="tool_calls", min_count=1
    ),
    V2EvalType.code_eval: CodeEvalProperties(code="pass"),
}


def _mock_eval_config(config_type: EvalConfigType) -> EvalConfig:
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = config_type
    return cfg


def _mock_v2_eval_config(v2_type: V2EvalType) -> EvalConfig:
    props = _V2_TYPE_TO_PROPS[v2_type]
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    return cfg


class TestEvalAdapterFromType:
    @pytest.mark.parametrize(
        "config_type", [EvalConfigType.g_eval, EvalConfigType.llm_as_judge]
    )
    def test_legacy_types_return_geval(self, config_type: EvalConfigType):
        cfg = _mock_eval_config(config_type)
        assert eval_adapter_from_type(cfg) is GEval

    def test_v2_raises_not_implemented(self):
        cfg = _mock_eval_config(EvalConfigType.v2)
        with pytest.raises(
            NotImplementedError,
            match="V2 eval configs use v2_eval_adapter_from_config",
        ):
            eval_adapter_from_type(cfg)

    def test_legacy_dispatch_v2_raises(self):
        cfg = _mock_eval_config(EvalConfigType.v2)
        with pytest.raises(NotImplementedError, match="v2_eval_adapter_from_config"):
            eval_adapter_from_type(cfg)

    def test_legacy_dispatch_unchanged(self):
        for ct in (EvalConfigType.g_eval, EvalConfigType.llm_as_judge):
            cfg = _mock_eval_config(ct)
            assert eval_adapter_from_type(cfg) is GEval


class TestV2EvalAdapterFromConfig:
    @pytest.mark.parametrize("v2_type", list(V2EvalType))
    def test_v2_dispatch_all_types_unimplemented(self, v2_type: V2EvalType):
        cfg = _mock_v2_eval_config(v2_type)
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            v2_eval_adapter_from_config(cfg)

    def test_v2_dispatch_rejects_legacy_config(self):
        cfg = _mock_eval_config(EvalConfigType.g_eval)
        with pytest.raises(ValueError, match="only accepts V2 configs"):
            v2_eval_adapter_from_config(cfg)
