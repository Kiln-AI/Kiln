from abc import ABC, abstractmethod
from typing import get_args

from pydantic import BaseModel

from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalConfigType,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
    V2EvalConfigProperties,
)

_V2_PROPERTY_TYPES: tuple[type[BaseModel], ...] = get_args(
    get_args(V2EvalConfigProperties)[0]
)


class BaseV2Eval(ABC):
    """Base class for V2 eval adapters -- separate from BaseEval because V2 adapters are synchronous, produce EvalScores dicts directly, and do not need the LLM-based score schema machinery."""

    def __init__(self, eval_config: EvalConfig) -> None:
        if eval_config.config_type != EvalConfigType.v2:
            raise ValueError("V2 eval requires a V2 config_type")
        if not isinstance(eval_config.properties, _V2_PROPERTY_TYPES):
            raise ValueError("V2 eval requires typed V2 properties")
        self.eval_config = eval_config
        self.properties = eval_config.properties

    @abstractmethod
    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        """Run the eval on the given input.

        Returns:
            (scores, skipped_reason, skipped_detail).
            If skipped_reason is set, scores should be {}.
        """
        ...
