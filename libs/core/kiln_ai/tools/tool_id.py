from enum import Enum
from typing import Annotated

from pydantic import AfterValidator

ToolId = Annotated[
    str,
    AfterValidator(lambda v: _check_tool_id(v)),
]
"""
A pydantic type that validates strings containing a valid tool ID.

Tool IDs can be one of:
- A kiln built-in tool name: kiln_tool::add_numbers
- More coming soon like MCP servers and kiln_project_tool::rag::RAG_CONFIG_ID
"""


class KilnBuiltInToolId(str, Enum):
    ADD_NUMBERS = "kiln_tool::add_numbers"
    SUBTRACT_NUMBERS = "kiln_tool::subtract_numbers"
    MULTIPLY_NUMBERS = "kiln_tool::multiply_numbers"
    DIVIDE_NUMBERS = "kiln_tool::divide_numbers"


def _check_tool_id(id: str) -> str:
    """
    Check that the tool ID is valid.
    """

    # Build in tools
    if id in KilnBuiltInToolId.__members__.values():
        return id

    raise ValueError(f"Invalid tool ID: {id}")
