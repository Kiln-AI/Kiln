from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.datamodel.eval import EvalConfigType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def eval_adapter_from_type(eval_config_type: EvalConfigType) -> type[BaseEval]:
    match eval_config_type:
        case EvalConfigType.g_eval:
            return GEval
        case EvalConfigType.llm_as_judge:
            # Also implemented by GEval
            return GEval
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(eval_config_type)
