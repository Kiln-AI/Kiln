import json
from typing import Any

from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as MCPTool

from kiln_ai.datamodel.external_tool_server import ExternalToolServer
from kiln_ai.datamodel.tool_id import MCP_REMOTE_TOOL_ID_PREFIX, ToolId
from kiln_ai.run_context import get_agent_run_id
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)
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

    async def toolcall_definition(self) -> ToolCallDefinition:
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

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        result = await self._call_tool(**kwargs)

        # MCP tool returned an application-level error - return it to the agent
        # instead of crashing the run. This allows the agent to respond gracefully.
        if result.isError:
            error_text = (
                " ".join(
                    block.text
                    for block in result.content
                    if isinstance(block, TextContent)
                )
                or "Unknown error"
            )
            return ToolCallResult(
                output=json.dumps({"isError": True, "error": error_text})
            )

        # If the tool returns structured content, return it as a JSON string
        if result.structuredContent is not None:
            if not isinstance(result.structuredContent, dict):
                raise ValueError("Tool returned invalid structured content")
            return ToolCallResult(
                output=json.dumps(result.structuredContent, ensure_ascii=False)
            )

        if not result.content:
            raise ValueError("Tool returned no content")

        # raise error if the first block is not a text block
        if not isinstance(result.content[0], TextContent):
            raise ValueError("First block must be a text block")

        # raise error if there is more than one content block
        if len(result.content) > 1:
            raise ValueError("Tool returned multiple content blocks, expected one")

        return ToolCallResult(output=result.content[0].text)

    async def input_schema(self) -> dict[str, Any]:
        # input schema is required
        await self._load_tool_properties()
        if not isinstance(self._parameters_schema, dict):
            raise ValueError("Tool input schema is invalid.")
        return self._parameters_schema

    async def output_schema(self) -> dict[str, Any] | None:
        # output schema is optional
        await self._load_tool_properties()
        if self._tool is None:
            raise ValueError("Tool output schema is invalid.")
        output_schema = self._tool.outputSchema
        if output_schema is None:
            return None
        if not isinstance(output_schema, dict):
            raise ValueError("Tool output schema is invalid.")
        return output_schema

    #  Call the MCP Tool
    async def _call_tool(self, **kwargs) -> CallToolResult:
        session_id = get_agent_run_id()
        if not session_id:
            raise RuntimeError(
                "MCP tool call attempted without an agent run context. "
                "This is a bug — tool calls should only happen during an agent run."
            )

        session = await MCPSessionManager.shared().get_or_create_session(
            self._tool_server_model, session_id
        )
        return await session.call_tool(
            name=await self.name(),
            arguments=kwargs,
        )

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
        session_id = get_agent_run_id()

        if session_id:
            session = await MCPSessionManager.shared().get_or_create_session(
                self._tool_server_model, session_id
            )
            tools = await session.list_tools()
        else:
            async with MCPSessionManager.shared().mcp_client(
                self._tool_server_model
            ) as session:
                tools = await session.list_tools()

        tool = next((tool for tool in tools.tools if tool.name == tool_name), None)
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        return tool
