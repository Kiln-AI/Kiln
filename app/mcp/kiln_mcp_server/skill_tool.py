"""The `kiln_skill` MCP tool: serves the Kiln skill, one file per call."""

import asyncio
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import AliasChoices, Field

from kiln_mcp_server.addresses import app_origin
from kiln_mcp_server.skill_files import SkillIndex, SkillPathError, read_skill
from kiln_mcp_server.texts import (
    PATH_DESCRIPTION,
    SKILL_TOOL_DESCRIPTION,
    ui_address_note,
)

SKILL_TOOL_NAME = "kiln_skill"


def _text_result(text: str, *, is_error: bool) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)], isError=is_error
    )


def _skill_tool_description(origin: str, ui_origin: str | None) -> str:
    if ui_origin is None or ui_origin == origin:
        return SKILL_TOOL_DESCRIPTION
    return SKILL_TOOL_DESCRIPTION + "\n\n" + ui_address_note(ui_origin, origin)


def register_skill_tool(
    mcp: FastMCP,
    *,
    bound_host: str,
    bound_port: int,
    ui_origin: str | None = None,
    index: SkillIndex | None = None,
) -> None:
    """Register `kiln_skill` on `mcp`.

    App links in the served files name the address Kiln is bound to, never the
    address in a request. When `ui_origin` is another address, the web UI is
    served there, and the tool description tells the agent to link to it.
    `index` defaults to the shipped skill tree.
    """
    origin = app_origin(bound_host, bound_port)

    @mcp.tool(
        name=SKILL_TOOL_NAME,
        description=_skill_tool_description(origin, ui_origin),
        structured_output=False,
        # Asks Claude Code to load the tool definition up front, not on demand.
        meta={"anthropic/alwaysLoad": True},
        annotations=ToolAnnotations(
            readOnlyHint=True, idempotentHint=True, openWorldHint=False
        ),
    )
    async def kiln_skill(
        path: Annotated[
            str | None,
            Field(
                description=PATH_DESCRIPTION,
                validation_alias=AliasChoices("path", "resource"),
            ),
        ] = None,
    ) -> CallToolResult:
        try:
            text = await asyncio.to_thread(read_skill, path, origin, index)
        except SkillPathError as e:
            return _text_result(e.message, is_error=True)
        return _text_result(text, is_error=False)
