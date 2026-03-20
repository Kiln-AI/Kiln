from dataclasses import dataclass
from typing import Dict

from litellm.types.utils import ChoiceLogprobs

from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


@dataclass
class RunOutput:
    output: Dict | str
    intermediate_outputs: Dict[str, str] | None
    output_logprobs: ChoiceLogprobs | None = None
    trace: list[ChatCompletionMessageParam] | None = None

    @property
    def is_toolcall_pending(self) -> bool:
        """True if the last message in the trace is an assistant message with pending tool calls."""
        if not self.trace:
            return False
        last_msg = self.trace[-1]
        return last_msg.get("role") == "assistant" and bool(last_msg.get("tool_calls"))
