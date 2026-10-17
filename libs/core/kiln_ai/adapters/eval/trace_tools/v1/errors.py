from kiln_ai.tools.base_tool import ToolCallError


class TraceToolUsageError(ToolCallError):
    """A trace tool call the judge can correct: bad arguments, or a response
    over the size limit. The message is written for the judge model."""
