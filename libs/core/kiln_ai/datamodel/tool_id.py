from enum import Enum
from typing import Annotated

from pydantic import AfterValidator

from kiln_ai.datamodel.basemodel import ID_TYPE

ToolId = Annotated[
    str,
    AfterValidator(lambda v: _check_tool_id(v)),
]
"""
A pydantic type that validates strings containing a valid tool ID.

Tool IDs can be one of:
- A kiln built-in tool name: kiln_tool::add_numbers
- A remote MCP tool: mcp::remote::<server_id>::<tool_name>
- A local MCP tool: mcp::local::<server_id>::<tool_name>
- A Kiln task tool: kiln_task::<server_id>
- More coming soon like kiln_project_tool::rag::RAG_CONFIG_ID
"""


class KilnBuiltInToolId(str, Enum):
    ADD_NUMBERS = "kiln_tool::add_numbers"
    SUBTRACT_NUMBERS = "kiln_tool::subtract_numbers"
    MULTIPLY_NUMBERS = "kiln_tool::multiply_numbers"
    DIVIDE_NUMBERS = "kiln_tool::divide_numbers"


MCP_REMOTE_TOOL_ID_PREFIX = "mcp::remote::"
RAG_TOOL_ID_PREFIX = "kiln_tool::rag::"
MCP_LOCAL_TOOL_ID_PREFIX = "mcp::local::"
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
                f"Invalid remote MCP tool ID: {id}. Expected format: 'mcp::remote::<server_id>::<tool_name>'."
            )
        return id

    # MCP local tools must have format: mcp::local::<server_id>::<tool_name>
    if id.startswith(MCP_LOCAL_TOOL_ID_PREFIX):
        server_id, tool_name = mcp_server_and_tool_name_from_id(id)
        if not server_id or not tool_name:
            raise ValueError(
                f"Invalid local MCP tool ID: {id}. Expected format: 'mcp::local::<server_id>::<tool_name>'."
            )
        return id

    # RAG tools must have format: kiln_tool::rag::<rag_config_id>
    if id.startswith(RAG_TOOL_ID_PREFIX):
        rag_config_id = rag_config_id_from_id(id)
        if not rag_config_id:
            raise ValueError(
                f"Invalid RAG tool ID: {id}. Expected format: 'kiln_tool::rag::<rag_config_id>'."
            )
        return id

    # Kiln task tools must have format: kiln_task::<server_id>
    if id.startswith(KILN_TASK_TOOL_ID_PREFIX):
        server_id = kiln_task_server_id_from_tool_id(id)
        if not server_id:
            raise ValueError(
                f"Invalid Kiln task tool ID: {id}. Expected format: 'kiln_task::<server_id>'."
            )
        return id

    raise ValueError(f"Invalid tool ID: {id}")


def mcp_server_and_tool_name_from_id(id: str) -> tuple[str, str]:
    """
    Get the tool server ID and tool name from the ID.
    """
    parts = id.split("::")
    if len(parts) != 4:
        # Determine if it's remote or local for the error message
        if id.startswith(MCP_REMOTE_TOOL_ID_PREFIX):
            raise ValueError(
                f"Invalid remote MCP tool ID: {id}. Expected format: 'mcp::remote::<server_id>::<tool_name>'."
            )
        elif id.startswith(MCP_LOCAL_TOOL_ID_PREFIX):
            raise ValueError(
                f"Invalid local MCP tool ID: {id}. Expected format: 'mcp::local::<server_id>::<tool_name>'."
            )
        else:
            raise ValueError(
                f"Invalid MCP tool ID: {id}. Expected format: 'mcp::(remote|local)::<server_id>::<tool_name>'."
            )
    return parts[2], parts[3]  # server_id, tool_name


def rag_config_id_from_id(id: str) -> str:
    """
    Get the RAG config ID from the ID.
    """
    parts = id.split("::")
    if not id.startswith(RAG_TOOL_ID_PREFIX) or len(parts) != 3:
        raise ValueError(
            f"Invalid RAG tool ID: {id}. Expected format: 'kiln_tool::rag::<rag_config_id>'."
        )
    return parts[2]


def build_rag_tool_id(rag_config_id: ID_TYPE) -> str:
    """Construct the tool ID for a RAG configuration."""

    return f"{RAG_TOOL_ID_PREFIX}{rag_config_id}"


def build_kiln_task_tool_id(server_id: ID_TYPE) -> str:
    """Construct the tool ID for a Kiln task server."""
    return f"{KILN_TASK_TOOL_ID_PREFIX}{server_id}"


def kiln_task_server_id_from_tool_id(tool_id: str) -> str:
    """
    Get the server ID from the tool ID.
    """
    if not tool_id.startswith(KILN_TASK_TOOL_ID_PREFIX):
        raise ValueError(
            f"Invalid Kiln task tool ID format: {tool_id}. Expected format: 'kiln_task::<server_id>'."
        )

    # Remove prefix and split on ::
    remaining = tool_id[len(KILN_TASK_TOOL_ID_PREFIX) :]
    if not remaining:
        raise ValueError(
            f"Invalid Kiln task tool ID format: {tool_id}. Expected format: 'kiln_task::<server_id>'."
        )
    parts = remaining.split("::")

    if len(parts) != 1 or not parts[0].strip():
        raise ValueError(
            f"Invalid Kiln task tool ID format: {tool_id}. Expected format: 'kiln_task::<server_id>'."
        )

    return parts[0]  # server_id
