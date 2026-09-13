"""Tools served by a episode.

A run config lists an environment's tools by id, ``kiln_tool::world::<world_id>::
<tool_name>``. While an episode of that world is active the registry resolves such an
id to ``OpenEnvToolProxy``: ``toolcall_definition()`` is what the environment reported
for the tool, and ``run()`` calls it through ``step(CallToolAction)`` on the episode's
session. Nothing is stored for these tools on disk; the environment is the source of
their names, schemas and behaviour.
"""

from __future__ import annotations

import json
from typing import Any

from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.datamodel.world import OpenEnvTool
from kiln_ai.run_context import EpisodeContext
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)


class OpenEnvToolProxy(KilnToolInterface):
    def __init__(
        self,
        tool_id: ToolId,
        tool: OpenEnvTool,
        context: EpisodeContext,
    ):
        self._tool_id = tool_id
        self._tool = tool
        self._ctx = context

    @property
    def env_tool(self) -> OpenEnvTool:
        return self._tool

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        return self._tool.name

    async def description(self) -> str:
        return self._tool.description

    async def toolcall_definition(self) -> ToolCallDefinition:
        return self._tool.toolcall_definition()

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        outcome = await self._ctx.session_manager.call_tool(
            self._ctx.episode, self._tool.name, dict(kwargs)
        )
        if outcome.error is not None:
            output = render_tool_error(
                outcome.error_code, outcome.error, outcome.error_details
            )
            if outcome.error_code and outcome.error_code not in WORLD_FAILURE_CODES:
                # The modelled product answering with an error of its own, which is an
                # ordinary answer: the real system's client would return the same body.
                return ToolCallResult(output=output)
            return ToolCallResult(
                output=output, is_error=True, error_message=outcome.error
            )
        output = render_tool_result(outcome.result)
        if isinstance(outcome.result, dict) and outcome.result.get("is_error") is True:
            return ToolCallResult(output=output, is_error=True, error_message=output)
        return ToolCallResult(output=output)


WORLD_FAILURE_CODES: frozenset[str] = frozenset(
    {"internal", "unknown_tool", "invalid_arguments", "world_gap"}
)
"""Error codes that mean the world itself failed, not the product it models.

Everything else is the modelled system speaking: an error the real system would also
return, which the real tool returns as an ordinary result. Keeping the two apart is what
lets one trace be compared against another taken against the real system."""


def render_tool_error(code: str | None, message: str, details: Any) -> str:
    """The text the model sees for an environment's tool error.

    A coded error renders as `{"error": {"code", "message", "details"}}`, always all
    three keys so the shape is stable whether or not there are details; an environment
    that reports no code renders the message alone."""
    if not code:
        return message
    return json.dumps(
        {"error": {"code": code, "message": message, "details": details}},
        ensure_ascii=False,
    )


def render_tool_result(result: Any) -> str:
    """The environment's tool result as the text the model sees.

    A FastMCP call result (`{"content": [...], "structured_content", "data", "is_error"}`)
    renders its native `data` when present, else its text content blocks; bare
    MCP-style content blocks are flattened to their text; anything else that is not
    already a string is serialized as JSON. `None` renders as `null`, the same text a
    tool that serializes its own result would show for an empty body."""
    if result is None:
        return "null"
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        if result.get("data") is not None:
            return render_tool_result(result["data"])
        blocks = result["content"]
        texts = [b.get("text") for b in blocks if isinstance(b, dict) and "text" in b]
        if texts and len(texts) == len(blocks):
            return "\n".join(str(t) for t in texts)
    if (
        isinstance(result, list)
        and result
        and all(isinstance(b, dict) and b.get("type") == "text" for b in result)
    ):
        return "\n".join(str(b.get("text", "")) for b in result)
    try:
        return json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(result)
