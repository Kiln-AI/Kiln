from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.datamodel.eval import EvalConfig, EvalConfigType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]:
    match eval_config.config_type:
        case EvalConfigType.g_eval:
            return GEval
        case EvalConfigType.llm_as_judge:
            return GEval
        case EvalConfigType.v2:
            raise NotImplementedError("V2 eval adapters are not yet implemented.")
        case _:
            raise_exhaustive_enum_error(eval_config.config_type)
