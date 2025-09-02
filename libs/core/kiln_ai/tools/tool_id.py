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


MCP_REMOTE_TOOL_ID_PREFIX = "mcp::remote::"
KILN_TASK_TOOL_ID_PREFIX = "kiln_task::"


def _check_tool_id(id: str) -> str:
    """
    Check that the tool ID is valid.
    """
    if not id or not isinstance(id, str):
        raise ValueError(f"Invalid tool ID: {id}")

    # Build in tools
    if id in KilnBuiltInToolId.__members__.values():
        return id

    # MCP remote tools must have format: mcp::remote::<server_id>::<tool_name>
    if id.startswith(MCP_REMOTE_TOOL_ID_PREFIX):
        server_id, tool_name = mcp_server_and_tool_name_from_id(id)
        if not server_id or not tool_name:
            raise ValueError(
                f"Invalid MCP remote tool ID: {id}. Expected format: 'mcp::remote::<server_id>::<tool_name>'."
            )
        return id

    # Kiln task tools must have format: kiln_task::<project_id>::<task_id>
    if id.startswith(KILN_TASK_TOOL_ID_PREFIX):
        # TODO: Check that the project ID is valid and the task ID is valid
        return id

    raise ValueError(f"Invalid tool ID: {id}")


def mcp_server_and_tool_name_from_id(id: str) -> tuple[str, str]:
    """
    Get the tool server ID and tool name from the ID.
    """
    parts = id.split("::")
    if len(parts) != 4:
        raise ValueError(
            f"Invalid MCP remote tool ID: {id}. Expected format: 'mcp::remote::<server_id>::<tool_name>'."
        )
    return parts[2], parts[3]  # server_id, tool_name


def kiln_task_id_from_tool_id(tool_id: str) -> str:
    """Extract task ID from Kiln task tool ID."""
    if not tool_id.startswith(KILN_TASK_TOOL_ID_PREFIX):
        raise ValueError(f"Invalid Kiln task tool ID format: {tool_id}")

    # Remove prefix and split on ::
    remaining = tool_id[len(KILN_TASK_TOOL_ID_PREFIX) :]
    parts = remaining.split("::")

    if len(parts) != 2:
        raise ValueError(f"Invalid Kiln task tool ID format: {tool_id}")

    return parts[1]  # parts[0] is project_id, parts[1] is task_id
