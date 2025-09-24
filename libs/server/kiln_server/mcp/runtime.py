"""Runtime helpers for configuring and running the Kiln MCP server."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Sequence

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

from .tool_registry import ToolContext

logger = logging.getLogger(__name__)

Transport = Literal["stdio", "sse", "streamable-http"]


def _format_unstructured_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, indent=2)
    except TypeError:
        return str(result)


def create_fastmcp_server(
    tool_contexts: Sequence[ToolContext],
    *,
    project_name: str | None,
    host: str,
    port: int,
    log_level: str,
    transport: Transport,
    mount_path: str | None,
) -> FastMCP:
    """Instantiate and configure a :class:`FastMCP` server for Kiln tools."""

    server_name = "Kiln MCP Server"
    if project_name:
        server_name = f"{server_name} ({project_name})"

    instructions = "Kiln MCP server exposing project tools."

    settings: dict[str, Any] = {
        "host": host,
        "port": port,
        "log_level": log_level.upper(),
    }
    if transport == "sse" and mount_path:
        settings["sse_path"] = mount_path
    if transport == "streamable-http" and mount_path:
        settings["streamable_http_path"] = mount_path

    server = FastMCP(name=server_name, instructions=instructions, **settings)

    tools_by_name = {context.definition.name: context for context in tool_contexts}

    @server._mcp_server.list_tools()
    async def _list_tools() -> list[Any]:
        return [context.definition for context in tool_contexts]

    @server._mcp_server.call_tool(validate_input=True)
    async def _call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object.")

        context = tools_by_name.get(name)
        if context is None:
            raise ValueError(f"Unknown tool requested: {name}")

        try:
            result = await context.resolution.tool.run(**arguments)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Tool %s failed", name)
            raise ValueError(str(exc)) from exc

        if context.requires_structured_output:
            if not isinstance(result, dict):
                raise ValueError(
                    f"Tool {name} returned non-dict output despite declaring an output schema."
                )
            return result

        return [TextContent(type="text", text=_format_unstructured_result(result))]

    return server


async def run_transport(
    server: FastMCP, transport: Transport, mount_path: str | None
) -> None:
    """Run the server using the selected transport."""

    if transport == "stdio":
        await server.run_stdio_async()
    elif transport == "sse":
        await server.run_sse_async(mount_path)
    elif transport == "streamable-http":
        await server.run_streamable_http_async()
    else:  # pragma: no cover - defensive branch
        raise ValueError(f"Unsupported transport: {transport}")
