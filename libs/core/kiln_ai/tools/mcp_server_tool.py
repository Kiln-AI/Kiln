import asyncio

from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as MCPTool

from kiln_ai.datamodel.external_tool import ExternalToolServer
from kiln_ai.tools.base_tool import KilnTool
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.tools.tool_id import MCP_REMOTE_TOOL_ID_PREFIX


class MCPServerTool(KilnTool):
    def __init__(self, model: ExternalToolServer, name: str):
        self._tool_server_model = model
        self._name = name
        self._tool: MCPTool | None = None

        #  Some properties are not available until the tool is loaded asynchronously
        super().__init__(
            tool_id=f"{MCP_REMOTE_TOOL_ID_PREFIX}{model.id}::{name}",
            name=name,
            description="Not Loaded",
            parameters_schema={
                "type": "object",
                "properties": {},
            },  # empty object for now, our JSON schema validation will fail if properties are missing
        )

    def run(self, **kwargs) -> str:
        result = asyncio.run(self._call_tool(**kwargs))
        if not result.content:
            return ""

        # raise error if the first block is not a text block
        if not isinstance(result.content[0], TextContent):
            raise ValueError("First block must be a text block")

        content: TextContent = result.content[0]
        return str(content.text)

    #  Call the MCP Tool
    async def _call_tool(self, **kwargs) -> CallToolResult:
        async with MCPSessionManager.shared().mcp_client(
            self._tool_server_model
        ) as session:
            result = await session.call_tool(
                name=self.name(),
                arguments=kwargs,
            )
            return result

    async def _load_tool_properties(self):
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
