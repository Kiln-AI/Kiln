from kiln_ai.adapters.errors import KilnRunError


class JudgeContextExceededError(Exception):
    """The judge model's context window filled up before it returned its scores.

    Not retryable: the same judge on the same trace runs out the same way.
    """

    def __init__(self, tool_call_count: int):
        if tool_call_count > 0:
            calls = "call" if tool_call_count == 1 else "calls"
            ran_out = (
                f"The judge model ran out of context after {tool_call_count:,} "
                f"trace tool {calls}."
            )
        else:
            ran_out = "The judge model ran out of context."
        super().__init__(
            f"{ran_out} Use a judge model with a larger context window, or a "
            "prompt that needs less of the trace."
        )
        self.tool_call_count = tool_call_count

    @classmethod
    def from_run_error(cls, error: KilnRunError) -> "JudgeContextExceededError":
        """Built from the judge run's failure, counting the tool results in its
        partial trace."""
        tool_results = sum(
            1 for message in error.partial_trace or [] if message.get("role") == "tool"
        )
        return cls(tool_results)
