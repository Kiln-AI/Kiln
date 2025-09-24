"""Utilities for selecting Kiln tools to expose via the MCP server."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.tool_id import RAG_TOOL_ID_PREFIX
from kiln_ai.tools.base_tool import KilnToolInterface

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResolution:
    """Represents a tool resolved from the Kiln project."""

    tool_id: str
    tool: KilnToolInterface


ToolFactory = Callable[[str, RagConfig], KilnToolInterface]


def _default_rag_tool_factory(tool_id: str, rag_config: RagConfig) -> KilnToolInterface:
    """Instantiate a :class:`~kiln_ai.tools.rag_tools.RagTool`."""

    from kiln_ai.tools.rag_tools import RagTool

    return RagTool(tool_id, rag_config)


def _is_archived(config: RagConfig) -> bool:
    """Check whether a RAG configuration is archived."""

    archived_flag = getattr(config, "archived", None)
    if archived_flag is not None:
        return bool(archived_flag)
    return bool(getattr(config, "is_archived", False))


def _iterate_rag_configs(project: Project) -> Iterable[RagConfig]:
    """Yield the project's RAG configurations in read-only mode."""

    return project.rag_configs(readonly=True)


def _build_rag_tool_id(rag_config: RagConfig) -> str:
    """Construct the tool ID for a RAG configuration."""

    return f"{RAG_TOOL_ID_PREFIX}{rag_config.id}"


def collect_project_tools(
    project: Project,
    allowed_tool_ids: Sequence[str] | None = None,
    *,
    rag_tool_factory: ToolFactory | None = None,
) -> list[ToolResolution]:
    """Collect the Kiln tools that should be exposed via MCP.

    Args:
        project: Project containing potential tools.
        allowed_tool_ids: Optional sequence of tool IDs to include. If provided,
            only matching tools will be returned.
        rag_tool_factory: Optional factory used to instantiate RAG tools. This is
            primarily intended for testing.

    Returns:
        A list of :class:`ToolResolution` objects describing the selected tools.

    Raises:
        ValueError: If ``allowed_tool_ids`` contains IDs that do not resolve to
            available tools.
    """

    factory = rag_tool_factory or _default_rag_tool_factory
    allowed_set = set(allowed_tool_ids or [])
    missing_ids = set(allowed_set)
    resolutions: list[ToolResolution] = []

    for rag_config in _iterate_rag_configs(project):
        if _is_archived(rag_config):
            logger.debug("Skipping archived RAG config %s", getattr(rag_config, "id", "<unknown>"))
            continue

        tool_id = _build_rag_tool_id(rag_config)

        if allowed_set and tool_id not in allowed_set:
            logger.debug("Skipping tool %s because it is not in the allowed list", tool_id)
            continue

        tool = factory(tool_id, rag_config)
        resolutions.append(ToolResolution(tool_id=tool_id, tool=tool))
        missing_ids.discard(tool_id)

    if missing_ids:
        raise ValueError(
            "Requested tool IDs were not found or are not eligible: " + ", ".join(sorted(missing_ids))
        )

    return resolutions
