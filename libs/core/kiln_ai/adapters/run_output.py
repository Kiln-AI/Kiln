from dataclasses import dataclass
from typing import Dict

from litellm.types.utils import ChoiceLogprobs
from openai.types.chat import ChatCompletionMessageParam


@dataclass
class RunOutput:
    output: Dict | str
    intermediate_outputs: Dict[str, str] | None
    output_logprobs: ChoiceLogprobs | None = None
    trace: list[ChatCompletionMessageParam] | None = None
