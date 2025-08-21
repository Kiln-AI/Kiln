from typing import Any, Dict

from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as MCPTool

from kiln_ai.datamodel.external_tool_server import ExternalToolServer
from kiln_ai.datamodel.tool_id import MCP_REMOTE_TOOL_ID_PREFIX, ToolId
from kiln_ai.tools.base_tool import KilnToolInterface
from kiln_ai.tools.mcp_session_manager import MCPSessionManager


class MCPServerTool(KilnToolInterface):
    def __init__(self, data_model: ExternalToolServer, name: str):
        self._tool_id = f"{MCP_REMOTE_TOOL_ID_PREFIX}{data_model.id}::{name}"
        self._tool_server_model = data_model
        self._name = name
        self._tool: MCPTool | None = None

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        await self._load_tool_properties()
        return self._description

    async def toolcall_definition(self) -> Dict[str, Any]:
        """Generate OpenAI-compatible tool definition."""
        await self._load_tool_properties()
        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": self._parameters_schema,
            },
        }

    async def run(self, **kwargs) -> Any:
        result = await self._call_tool(**kwargs)

        if result.isError:
            raise ValueError(
                f"Tool {await self.name()} returned an error: {result.content}"
            )

        if not result.content:
            raise ValueError("Tool returned no content")

        # raise error if the first block is not a text block
        if not isinstance(result.content[0], TextContent):
            raise ValueError("First block must be a text block")

        # raise error if there is more than one content block
        if len(result.content) > 1:
            raise ValueError("Tool returned multiple content blocks, expected one")

        return result.content[0].text

    #  Call the MCP Tool
    async def _call_tool(self, **kwargs) -> CallToolResult:
        async with MCPSessionManager.shared().mcp_client(
            self._tool_server_model
        ) as session:
            result = await session.call_tool(
                name=await self.name(),
                arguments=kwargs,
            )
            return result

    async def _load_tool_properties(self):
        if self._tool is not None:
            return

        tool = await self._get_tool(self._name)
        self._tool = tool
        self._description = tool.description or "N/A"
        self._parameters_schema = tool.inputSchema or {
            "type": "object",
            "properties": {},
        }

    #  Get the MCP Tool from the server
    async def _get_tool(self, tool_name: str) -> MCPTool:
        async with MCPSessionManager.shared().mcp_client(
            self._tool_server_model
        ) as session:
            tools = await session.list_tools()

        tool = next((tool for tool in tools.tools if tool.name == tool_name), None)
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        return tool
