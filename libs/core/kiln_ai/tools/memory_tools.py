"""KilnToolInterface adapters exposing the six assistant-memory operations to the
Kiln agent harness, bound to the current run's project.

This is Phase 3 of the agent_memory project (cuttable): a thin, mechanical adapter
over kiln_ai.memory.MemoryStore. scope stays an explicit tool parameter on every
write — no injection — so this surface behaves identically to the stdio MCP server.
All six are agent-available with no approval gate (a tool in a run config's
tools_config is callable by the agent; there is no per-tool approval layer in core).

The tool descriptions are prompts and part of the deliverable; they carry the write
discipline and retrieval semantics from the functional spec.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import ValidationError

from kiln_ai.datamodel.memory import Memory
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.tool_id import ToolId, memory_operation_from_tool_id
from kiln_ai.memory import MemoryListResult, MemoryStore
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)

# Shared JSON-schema fragments for tool parameters.
_SCOPE_SCHEMA = {
    "type": "string",
    "description": (
        "Opaque scope string. Conventions: 'project' for project-wide knowledge "
        "(constraints, environment facts); 'task::<task_id>' for task-scoped work. "
        "Required on writes — there is no default."
    ),
}
_TAGS_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Snake_case tags (no spaces). Used for filtering.",
}


class _MemoryTool(KilnToolInterface):
    """Base for the six memory tools. Subclasses set name/description/schema and run()."""

    _name: ClassVar[str] = ""
    _description: ClassVar[str] = ""
    _parameters_schema: ClassVar[dict[str, Any]] = {}

    def __init__(self, tool_id: str, store: MemoryStore):
        self._tool_id = tool_id
        self._store = store

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        return self._description

    async def toolcall_definition(self) -> ToolCallDefinition:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": self._parameters_schema,
            },
        }

    # --- helpers ---

    @staticmethod
    def _record(memory: Memory) -> dict[str, Any]:
        return {
            "id": memory.id,
            "overview": memory.overview,
            "content": memory.content,
            "tags": list(memory.tags),
            "scope": memory.scope,
            "created_at": memory.created_at.isoformat(),
            "created_by": memory.created_by,
        }

    @staticmethod
    def _ok(payload: Any) -> ToolCallResult:
        return ToolCallResult(output=json.dumps(payload, default=str))

    @staticmethod
    def _error(exc: Exception) -> ToolCallResult:
        message = str(exc)
        return ToolCallResult(output=message, is_error=True, error_message=message)


class SaveMemoryTool(_MemoryTool):
    _name: ClassVar[str] = "save_memory"
    _description: ClassVar[str] = (
        "Record a durable memory of your work on this project so it survives "
        "context loss. Save memory-worthy findings: probe results with their "
        "evidence level, rejected approaches and WHY they failed, API quirks, "
        "customer/environment constraints and preferences, future ideas, and "
        "rolling session state. Record observations WITH their conditions "
        "(e.g. 'batch API 429'd at 50rps on 07-04'), never universal rules. "
        "List related memories first and update instead of duplicating. The "
        "overview must let a future reader decide whether to fetch the content; "
        "for a very short memory the overview IS the whole memory (leave content null)."
    )
    _parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "overview": {
                "type": "string",
                "description": (
                    "One-line summary (<=140 chars, no newlines) written so a future "
                    "reader can decide whether to fetch the full content."
                ),
            },
            "scope": _SCOPE_SCHEMA,
            "content": {
                "type": "string",
                "description": (
                    "The memory body (<=2000 chars): the finding/fact/decision with "
                    "its conditions and evidence level, citing related Kiln records as "
                    "prose IDs (e.g. 'run_config 184623901234'). Omit when the overview "
                    "says everything."
                ),
            },
            "tags": _TAGS_SCHEMA,
        },
        "required": ["overview", "scope"],
    }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        try:
            memory = self._store.save_memory(
                overview=kwargs["overview"],
                scope=kwargs["scope"],
                content=kwargs.get("content"),
                tags=kwargs.get("tags"),
            )
        except (ValidationError, ValueError) as e:
            return self._error(e)
        return self._ok({"id": memory.id, "memory": self._record(memory)})


class ListMemoriesTool(_MemoryTool):
    _name: ClassVar[str] = "list_memories"
    _description: ClassVar[str] = (
        "List memory summaries (id, overview, tags, scope, content_length, "
        "created_at, created_by), newest first. content_length 0 means the "
        "overview is the entire memory — no need to fetch it. Filters combine with "
        "AND: scope is an exact match; tags requires the memory to have ALL listed "
        "tags (use multiple calls for OR); content_match is a case-insensitive regex "
        "over overview + content. When the result is truncated it says how many more "
        "match and how to narrow by tag."
    )
    _parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": "Exact-match scope filter. Omit for all scopes.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Memory must have ALL of these tags (AND). Omit for no tag filter.",
            },
            "content_match": {
                "type": "string",
                "description": "Case-insensitive regex over overview + content.",
            },
            "limit": {"type": "integer", "description": "Max rows (default 50)."},
            "offset": {"type": "integer", "description": "Rows to skip (default 0)."},
        },
        "required": [],
    }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        try:
            result = self._store.list_memories(
                scope=kwargs.get("scope"),
                tags=kwargs.get("tags"),
                content_match=kwargs.get("content_match"),
                limit=kwargs.get("limit", 50),
                offset=kwargs.get("offset", 0),
            )
        except (ValidationError, ValueError) as e:
            return self._error(e)
        payload: dict[str, Any] = {
            "memories": [
                listing.model_dump(mode="json") for listing in result.listings
            ],
            "matched": result.matched,
        }
        if result.remaining > 0:
            payload["note"] = _render_truncation_note(result)
        return self._ok(payload)


class GetMemoriesTool(_MemoryTool):
    _name: ClassVar[str] = "get_memories"
    _description: ClassVar[str] = (
        "Fetch full memory records by id. content_length 0 in a listing means the "
        "overview is the entire memory — no need to fetch. Fetch in batches, not all "
        "at once. Unknown ids are silently omitted from the result."
    )
    _parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The memory ids to fetch.",
            }
        },
        "required": ["ids"],
    }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        ids = kwargs.get("ids") or []
        records = self._store.get_memories(list(ids))
        return self._ok({"memories": [self._record(m) for m in records]})


class UpdateMemoryTool(_MemoryTool):
    _name: ClassVar[str] = "update_memory"
    _description: ClassVar[str] = (
        "Replace provided fields on an existing memory (omitted fields are "
        "untouched). Prefer adding a 'stale' tag plus a new correction memory over "
        "rewriting someone else's content; the main legitimate rewrite case is a "
        "rolling session-state memory. Passing an empty content clears it. Conflicts "
        "resolve last-writer-wins."
    )
    _parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "The memory id to update."},
            "overview": {
                "type": "string",
                "description": "New one-line summary (<=140 chars, no newlines).",
            },
            "content": {
                "type": "string",
                "description": "New body (<=2000 chars). Empty string clears it.",
            },
            "tags": _TAGS_SCHEMA,
            "scope": _SCOPE_SCHEMA,
        },
        "required": ["id"],
    }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        memory_id = kwargs.get("id")
        if not memory_id:
            return self._error(ValueError("id is required"))
        updates = {
            key: kwargs[key]
            for key in ("overview", "content", "tags", "scope")
            if key in kwargs
        }
        try:
            memory = self._store.update_memory(memory_id, **updates)
        except (ValidationError, ValueError) as e:
            return self._error(e)
        return self._ok({"memory": self._record(memory)})


class DeleteMemoryTool(_MemoryTool):
    _name: ClassVar[str] = "delete_memory"
    _description: ClassVar[str] = (
        "Hard-delete a memory by id. For confirmed junk only; prefer tagging a "
        "'wrong but instructive' memory as 'stale' instead of deleting it."
    )
    _parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "The memory id to delete."}
        },
        "required": ["id"],
    }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        memory_id = kwargs.get("id")
        if not memory_id:
            return self._error(ValueError("id is required"))
        try:
            self._store.delete_memory(memory_id)
        except ValueError as e:
            return self._error(e)
        return self._ok({"deleted": memory_id})


class MemorySummaryTool(_MemoryTool):
    _name: ClassVar[str] = "memory_summary"
    _description: ClassVar[str] = (
        "Cheap orientation with no record content: per-scope counts, newest "
        "timestamp, and tag cardinalities. Call this at session start before "
        "targeted list_memories calls. Omit scope for all scopes."
    )
    _parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": "Limit to one scope. Omit for all scopes.",
            }
        },
        "required": [],
    }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        summary = self._store.memory_summary(scope=kwargs.get("scope"))
        return self._ok(summary.model_dump(mode="json", exclude_none=True))


_TOOL_CLASSES: dict[str, type[_MemoryTool]] = {
    "save": SaveMemoryTool,
    "list": ListMemoriesTool,
    "get": GetMemoriesTool,
    "update": UpdateMemoryTool,
    "delete": DeleteMemoryTool,
    "summary": MemorySummaryTool,
}


def _render_truncation_note(result: MemoryListResult) -> str:
    if result.remaining_tag_counts:
        tag_str = ", ".join(
            f"{tag}({count})" for tag, count in result.remaining_tag_counts.items()
        )
        return (
            f"{result.remaining} more — narrow with scope, tags, or content_match. "
            f"Remaining by tag: {tag_str}"
        )
    return f"{result.remaining} more — narrow with scope, tags, or content_match."


def memory_tool_from_id(tool_id: str, project: Project) -> KilnToolInterface:
    """Resolve a kiln_tool::memory::<op> id to a tool bound to the project's store."""
    operation = memory_operation_from_tool_id(tool_id)
    store = MemoryStore(project)
    return _TOOL_CLASSES[operation](tool_id, store)
