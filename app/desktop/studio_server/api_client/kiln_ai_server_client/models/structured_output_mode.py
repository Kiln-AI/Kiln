from enum import Enum


class StructuredOutputMode(str, Enum):
    DEFAULT = "default"
    FUNCTION_CALLING = "function_calling"
    FUNCTION_CALLING_WEAK = "function_calling_weak"
    JSON_CUSTOM_INSTRUCTIONS = "json_custom_instructions"
    JSON_INSTRUCTIONS = "json_instructions"
    JSON_INSTRUCTION_AND_OBJECT = "json_instruction_and_object"
    JSON_MODE = "json_mode"
    JSON_SCHEMA = "json_schema"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
