from enum import Enum, IntEnum


class Priority(IntEnum):
    """Defines priority levels for tasks and requirements, where P0 is highest priority."""

    p0 = 0
    p1 = 1
    p2 = 2
    p3 = 3


# Only one rating type for now, but this allows for extensibility if we want to add more in the future
class TaskOutputRatingType(str, Enum):
    """Defines the types of rating systems available for task outputs."""

    five_star = "five_star"
    pass_fail = "pass_fail"
    pass_fail_critical = "pass_fail_critical"
    custom = "custom"


class StructuredOutputMode(str, Enum):
    """
    Enumeration of supported structured output modes.

    - default: let the adapter decide
    - json_schema: request json using API capabilities for json_schema
    - function_calling: request json using API capabilities for function calling
    - json_mode: request json using API's JSON mode, which should return valid JSON, but isn't checking/passing the schema
    - json_instructions: append instructions to the prompt to request json matching the schema. No API capabilities are used. You should have a custom parser on these models as they will be returning strings.
    - json_instruction_and_object: append instructions to the prompt to request json matching the schema. Also request the response as json_mode via API capabilities (returning dictionaries).
    - json_custom_instructions: The model should output JSON, but custom instructions are already included in the system prompt. Don't append additional JSON instructions.
    """

    default = "default"
    json_schema = "json_schema"
    function_calling_weak = "function_calling_weak"
    function_calling = "function_calling"
    json_mode = "json_mode"
    json_instructions = "json_instructions"
    json_instruction_and_object = "json_instruction_and_object"
    json_custom_instructions = "json_custom_instructions"


class FineTuneStatusType(str, Enum):
    """
    The status type of a fine-tune (running, completed, failed, etc).
    """

    unknown = "unknown"  # server error
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class FinetuneDataStrategy(str, Enum):
    final_only = "final_only"
    final_and_intermediate = "final_and_intermediate"
