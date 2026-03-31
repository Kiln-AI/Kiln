from dataclasses import dataclass
from typing import Dict

from litellm.types.utils import ChoiceLogprobs

from kiln_ai.utils.open_ai_types import (
    ChatCompletionMessageParam,
    trace_has_pending_client_tool_calls,
)


@dataclass
class RunOutput:
    output: Dict | str
    intermediate_outputs: Dict[str, str] | None
    output_logprobs: ChoiceLogprobs | None = None
    trace: list[ChatCompletionMessageParam] | None = None

    @property
    def is_toolcall_pending(self) -> bool:
        """True if the trace ends with an assistant message awaiting client tool execution."""
        return trace_has_pending_client_tool_calls(self.trace)
