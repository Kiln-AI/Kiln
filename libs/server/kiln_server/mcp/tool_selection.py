"""Utilities for selecting Kiln tools to expose via the MCP server."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from kiln_ai.datamodel.external_tool_server import ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.tool_id import build_kiln_task_tool_id, build_rag_tool_id
from kiln_ai.tools.base_tool import KilnToolInterface
from kiln_ai.tools.kiln_task_tool import KilnTaskTool
from kiln_ai.tools.rag_tools import RagTool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResolution:
    """Represents a tool resolved from the Kiln project."""

    tool_id: str
    tool: KilnToolInterface


def collect_project_tools(
    project: Project,
    allowed_tool_ids: Sequence[str] | None = None,
) -> list[ToolResolution]:
    """Collect the Kiln tools that should be exposed via MCP.

    Args:
        project: Project containing potential tools.
        allowed_tool_ids: Optional sequence of tool IDs to include. If provided,
            only matching tools will be returned.

    Returns:
        A list of :class:`ToolResolution` objects describing the selected tools.

    Raises:
        ValueError: If ``allowed_tool_ids`` contains IDs that do not resolve to
            available tools.
    """

    allowed_set = set(allowed_tool_ids or [])
    missing_ids = set(allowed_set)
    resolutions: list[ToolResolution] = []

    for rag_config in project.rag_configs(readonly=True):
        if rag_config.is_archived:
            logger.debug(
                "Skipping archived RAG config %s",
                getattr(rag_config, "id", "<unknown>"),
            )
            continue

        tool_id = build_rag_tool_id(rag_config.id)

        if allowed_set and tool_id not in allowed_set:
            logger.debug(
                "Skipping tool %s because it is not in the allowed list", tool_id
            )
            continue

        tool = RagTool(tool_id, rag_config)
        resolutions.append(ToolResolution(tool_id=tool_id, tool=tool))
        missing_ids.discard(tool_id)

    for server in project.external_tool_servers(readonly=True):
        if server.type != ToolServerType.kiln_task:
            continue

        tool_id = build_kiln_task_tool_id(server.id)

        if allowed_set and tool_id not in allowed_set:
            logger.debug(
                "Skipping tool %s because it is not in the allowed list", tool_id
            )
            continue

        if project.id is None:
            raise ValueError("Project ID is required")

        tool = KilnTaskTool(project.id, tool_id, server)
        resolutions.append(ToolResolution(tool_id=tool_id, tool=tool))
        missing_ids.discard(tool_id)

    if missing_ids:
        raise ValueError(
            "Requested tool IDs were not found or are archived: "
            + ", ".join(sorted(missing_ids))
        )

    return resolutions
