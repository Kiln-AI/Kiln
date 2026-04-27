from enum import Enum


class ClientChatMessageRole(str, Enum):
    TOOL = "tool"
    USER = "user"

    def __str__(self) -> str:
        return str(self.value)
