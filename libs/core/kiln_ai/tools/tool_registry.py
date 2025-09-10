from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import (
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    mcp_server_and_tool_name_from_id,
)
from kiln_ai.tools.base_tool import KilnToolInterface
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.tools.mcp_server_tool import MCPServerTool
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def tool_from_id(tool_id: str, task: Task | None = None) -> KilnToolInterface:
    """
    Get a tool from its ID.
    """
    # Check built-in tools
    if tool_id in [member.value for member in KilnBuiltInToolId]:
        typed_tool_id = KilnBuiltInToolId(tool_id)
        match typed_tool_id:
            case KilnBuiltInToolId.ADD_NUMBERS:
                return AddTool()
            case KilnBuiltInToolId.SUBTRACT_NUMBERS:
                return SubtractTool()
            case KilnBuiltInToolId.MULTIPLY_NUMBERS:
                return MultiplyTool()
            case KilnBuiltInToolId.DIVIDE_NUMBERS:
                return DivideTool()
            case _:
                raise_exhaustive_enum_error(typed_tool_id)

    # Check MCP Server Tools
    if tool_id.startswith((MCP_REMOTE_TOOL_ID_PREFIX, MCP_LOCAL_TOOL_ID_PREFIX)):
        project = task.parent_project() if task is not None else None
        if project is None:
            raise ValueError(
                f"Unable to resolve tool from id: {tool_id}. Requires a parent project/task."
            )

        # Get the tool server ID and tool name from the ID
        tool_server_id, tool_name = mcp_server_and_tool_name_from_id(tool_id)

        server = next(
            (
                server
                for server in project.external_tool_servers()
                if server.id == tool_server_id
            ),
            None,
        )
        if server is None:
            raise ValueError(
                f"External tool server not found: {tool_server_id} in project ID {project.id}"
            )

        return MCPServerTool(server, tool_name)

    raise ValueError(f"Tool ID {tool_id} not found in tool registry")
