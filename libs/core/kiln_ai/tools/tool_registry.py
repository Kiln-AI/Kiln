from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import (
    KILN_TASK_TOOL_ID_PREFIX,
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    RAG_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    kiln_task_server_id_from_tool_id,
    mcp_server_and_tool_name_from_id,
    rag_config_id_from_id,
)
from kiln_ai.tools.base_tool import KilnToolInterface, ToolCallDefinition
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.tools.kiln_task_tool import KilnTaskTool
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

    # Check if this looks like an MCP or Kiln Task tool ID that requires a project
    is_mcp_tool = tool_id.startswith(
        (MCP_REMOTE_TOOL_ID_PREFIX, MCP_LOCAL_TOOL_ID_PREFIX)
    )
    is_kiln_task_tool = tool_id.startswith(KILN_TASK_TOOL_ID_PREFIX)

    if is_mcp_tool or is_kiln_task_tool:
        project = task.parent_project() if task is not None else None
        if project is None or project.id is None:
            raise ValueError(
                f"Unable to resolve tool from id: {tool_id}. Requires a parent project/task."
            )

        # Check MCP Server Tools
        if is_mcp_tool:
            # Get the tool server ID and tool name from the ID
            tool_server_id, tool_name = mcp_server_and_tool_name_from_id(
                tool_id
            )  # Fixed function name

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

        # Check Kiln Task Tools
        if is_kiln_task_tool:
            server_id = kiln_task_server_id_from_tool_id(tool_id)

            server = next(
                (
                    server
                    for server in project.external_tool_servers()
                    if server.id == server_id
                ),
                None,
            )
            if server is None:
                raise ValueError(
                    f"Kiln Task External tool server not found: {server_id} in project ID {project.id}"
                )

            return KilnTaskTool(project.id, tool_id, server)

    elif tool_id.startswith(RAG_TOOL_ID_PREFIX):
        project = task.parent_project() if task is not None else None
        if project is None:
            raise ValueError(
                f"Unable to resolve tool from id: {tool_id}. Requires a parent project/task."
            )

        rag_config_id = rag_config_id_from_id(tool_id)
        rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
        if rag_config is None:
            raise ValueError(
                f"RAG config not found: {rag_config_id} in project {project.id} for tool {tool_id}"
            )

        # Lazy import to avoid circular dependency
        from kiln_ai.tools.rag_tools import RagTool

        return RagTool(tool_id, rag_config)

    raise ValueError(f"Tool ID {tool_id} not found in tool registry")


async def tool_definitions_from_ids(
    tool_ids: list[str], task: Task | None = None
) -> list[ToolCallDefinition]:
    """
    Get OpenAI-compatible tool definitions from a list of tool IDs.
    """
    tool_definitions = []
    for tool_id in tool_ids:
        try:
            tool = tool_from_id(tool_id, task)
            tool_def = await tool.toolcall_definition()
            tool_definitions.append(tool_def)
        except Exception as e:
            raise ValueError(
                f"Failed to get tool definition for tool ID: {tool_id}. Original error: {e}"
            )
    return tool_definitions
