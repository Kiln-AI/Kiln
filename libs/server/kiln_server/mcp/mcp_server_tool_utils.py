"""Utilities for preparing Kiln tools for the MCP server."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Sequence

from kiln_ai.tools.base_tool import KilnToolInterface
from mcp.types import Tool

from .tool_selection import ToolResolution

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolContext:
    """Context required to expose a Kiln tool via MCP."""

    resolution: ToolResolution
    definition: Tool
    requires_structured_output: bool


async def _resolve_output_schema(tool: KilnToolInterface) -> dict[str, Any] | None:
    """Resolve an optional output schema from a tool.

    The ``KilnToolInterface`` does not require tools to expose an ``output_schema``
    attribute, but some tools may offer it. The attribute can be a dictionary, a
    callable returning a dictionary, or an awaitable that yields a dictionary.
    Only non-empty dictionaries are considered valid schemas.
    """

    candidate = getattr(tool, "output_schema", None)
    if candidate is None:
        return None

    value: Any = candidate
    if inspect.iscoroutinefunction(candidate):
        value = await candidate()  # type: ignore[func-returns-value]
    elif inspect.isawaitable(candidate):
        value = await candidate  # type: ignore[func-returns-value]
    elif callable(candidate):
        value = candidate()
        if inspect.isawaitable(value):
            value = await value

    if isinstance(value, dict) and value:
        return value

    logger.debug("Ignoring non-dict output schema for tool %s", tool)
    return None


async def _build_tool_context(resolution: ToolResolution) -> ToolContext:
    tool = resolution.tool
    definition = await tool.toolcall_definition()
    function_def = definition.get("function", {})

    name = function_def.get("name")
    description = function_def.get("description")

    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Tool {resolution.tool_id} returned an invalid name")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"Tool {resolution.tool_id} returned an invalid description")

    parameters = function_def.get("parameters")
    if not isinstance(parameters, dict) or not parameters:
        parameters = {"type": "object", "properties": {}}

    output_schema = await _resolve_output_schema(tool)

    tool_definition = Tool(
        name=name,
        description=description,
        inputSchema=parameters,
        outputSchema=output_schema,
        _meta={"kiln_tool_id": resolution.tool_id},
    )

    return ToolContext(
        resolution=resolution,
        definition=tool_definition,
        requires_structured_output=output_schema is not None,
    )


async def prepare_tool_contexts(
    resolutions: Sequence[ToolResolution],
) -> list[ToolContext]:
    """Prepare ``ToolContext`` objects for the provided tool resolutions."""

    contexts: list[ToolContext] = []
    seen_names: set[str] = set()

    for resolution in resolutions:
        context = await _build_tool_context(resolution)
        tool_name = context.definition.name
        if tool_name in seen_names:
            raise ValueError(
                f"Duplicate tool name detected: {tool_name}. A MCP server can't expose 2 tools with the same name. Either archive the duplicate tool in Kiln's UI, or only specify one tool with each name for MCP using the --tool-ids flag of the kiln_mcp command."
            )
        seen_names.add(tool_name)
        contexts.append(context)

    return contexts
