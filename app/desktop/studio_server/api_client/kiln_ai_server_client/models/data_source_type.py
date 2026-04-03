from enum import Enum


class DataSourceType(str, Enum):
    FILE_IMPORT = "file_import"
    HUMAN = "human"
    SYNTHETIC = "synthetic"
    TOOL_CALL = "tool_call"

    def __str__(self) -> str:
        return str(self.value)
