from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.adapters.eval.registry import eval_adapter_from_type
from kiln_ai.datamodel.eval import EvalConfig, EvalConfigType


def _mock_eval_config(config_type: EvalConfigType) -> EvalConfig:
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = config_type
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
            NotImplementedError, match="V2 eval adapters are not yet implemented"
        ):
            eval_adapter_from_type(cfg)
