from enum import Enum


class ToolInvocationState(str, Enum):
    CALL = "call"
    PARTIAL_CALL = "partial-call"
    RESULT = "result"

    def __str__(self) -> str:
        return str(self.value)
