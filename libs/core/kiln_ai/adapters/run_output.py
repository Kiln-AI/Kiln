from dataclasses import dataclass
from typing import Any, Dict

from litellm.types.utils import ChoiceLogprobs


@dataclass
class RunOutput:
    output: Dict | str
    intermediate_outputs: Dict[str, str] | None
    output_logprobs: ChoiceLogprobs | None = None
    trace: list[Dict[str, Any]] | None = None
