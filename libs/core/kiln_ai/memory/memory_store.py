from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from kiln_ai.datamodel.basemodel import KilnParentModel
from kiln_ai.datamodel.memory import Memory


class MemoryNotFoundError(ValueError):
    """Raised when an update/delete targets an id that is not in the store."""

    def __init__(self, memory_id: str):
        self.memory_id = memory_id
        super().__init__(f"No memory with id '{memory_id}' in this store.")


class InvalidContentMatchError(ValueError):
    """Raised when list_memories is called with an invalid content_match regex."""

    def __init__(self, message: str):
        super().__init__(f"Invalid content_match regex: {message}")


class MemoryListing(BaseModel):
    """A single row in a list_memories result. Carries content_length, not content."""

    id: str
    overview: str
    tags: list[str]
    scope: str
    content_length: int
    created_at: datetime
    created_by: str


class MemoryListResult(BaseModel):
    """A page of list_memories results plus the truncation nudge data.

    remaining_tag_counts is computed over the records beyond this page (the
    not-returned remainder), sorted by count descending. Adapters render it into
    a prompt-facing nudge string like "62 more — filter by tag: probe(18), ...".
    """

    listings: list[MemoryListing]
    matched: int
    remaining: int
    remaining_tag_counts: dict[str, int]


class ScopeSummary(BaseModel):
    scope: str
    count: int
    newest: datetime
    tags: dict[str, int]
    untagged: int | None = None


class MemorySummary(BaseModel):
    total: int
    scopes: list[ScopeSummary]


# Sentinel distinguishing "field omitted" from "field explicitly set to None" in
# update_memory (so content=None clears content while omitting it leaves it as-is).
_UNSET: Any = object()


class MemoryStore:
    """Store-agnostic memory operations over a (parent model + Memory class) binding.

    Assumes nothing about the parent beyond: it is a saved KilnParentModel (has a
    path) under which memory_model is registered. v1 binds Project + Memory; a
    future per-Task store binds Task + a Memory subclass with no change here.
    """

    def __init__(self, parent: KilnParentModel, memory_model: type[Memory] = Memory):
        if parent.path is None:
            raise ValueError(
                "MemoryStore requires a saved parent (parent.path must be set)."
            )
        self.parent = parent
        self.memory_model = memory_model

    def _all(self) -> list[Memory]:
        return self.memory_model.all_children_of_parent_path(
            self.parent.path, readonly=True
        )

    def save_memory(
        self,
        *,
        overview: str,
        scope: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        memory = self.memory_model(
            parent=self.parent,
            overview=overview,
            scope=scope,
            content=content,
            tags=list(tags) if tags else [],
        )
        memory.save_to_file()
        return memory

    def get_memories(self, ids: list[str]) -> list[Memory]:
        found = self.memory_model.from_ids_and_parent_path(set(ids), self.parent.path)
        return list(found.values())

    def update_memory(
        self,
        memory_id: str,
        *,
        overview: Any = _UNSET,
        content: Any = _UNSET,
        tags: Any = _UNSET,
        scope: Any = _UNSET,
    ) -> Memory:
        memory = self.memory_model.from_id_and_parent_path(memory_id, self.parent.path)
        if memory is None:
            raise MemoryNotFoundError(memory_id)
        if overview is not _UNSET:
            memory.overview = overview
        if content is not _UNSET:
            memory.content = content
        if tags is not _UNSET:
            memory.tags = list(tags) if tags else []
        if scope is not _UNSET:
            memory.scope = scope
        memory.save_to_file()
        return memory

    def delete_memory(self, memory_id: str) -> None:
        memory = self.memory_model.from_id_and_parent_path(memory_id, self.parent.path)
        if memory is None:
            raise MemoryNotFoundError(memory_id)
        memory.delete()

    def list_memories(
        self,
        *,
        scope: str | None = None,
        tags: list[str] | None = None,
        content_match: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MemoryListResult:
        memories = self._all()

        if scope is not None:
            memories = [m for m in memories if m.scope == scope]
        if tags:
            wanted = set(tags)
            memories = [m for m in memories if wanted.issubset(set(m.tags))]
        if content_match is not None:
            try:
                pattern = re.compile(content_match, re.IGNORECASE)
            except re.error as e:
                raise InvalidContentMatchError(str(e))
            memories = [
                m
                for m in memories
                if pattern.search(m.overview)
                or (m.content is not None and pattern.search(m.content))
            ]

        # Newest-first, with a stable tiebreak on id so paging is deterministic.
        memories.sort(key=lambda m: (m.created_at, m.id or ""), reverse=True)

        matched = len(memories)
        page = memories[offset : offset + limit]
        remainder = memories[offset + len(page) :]

        remaining_counts: Counter[str] = Counter()
        for memory in remainder:
            remaining_counts.update(memory.tags)

        return MemoryListResult(
            listings=[self._to_listing(m) for m in page],
            matched=matched,
            remaining=len(remainder),
            remaining_tag_counts=dict(remaining_counts.most_common()),
        )

    def memory_summary(self, scope: str | None = None) -> MemorySummary:
        memories = self._all()
        if scope is not None:
            memories = [m for m in memories if m.scope == scope]

        groups: dict[str, list[Memory]] = {}
        for memory in memories:
            groups.setdefault(memory.scope, []).append(memory)

        scope_summaries: list[ScopeSummary] = []
        for scope_name, group in groups.items():
            tag_counts: Counter[str] = Counter()
            untagged = 0
            for memory in group:
                if memory.tags:
                    tag_counts.update(memory.tags)
                else:
                    untagged += 1
            scope_summaries.append(
                ScopeSummary(
                    scope=scope_name,
                    count=len(group),
                    newest=max(m.created_at for m in group),
                    tags=dict(tag_counts.most_common()),
                    untagged=untagged if untagged > 0 else None,
                )
            )

        scope_summaries.sort(key=lambda s: s.newest, reverse=True)
        return MemorySummary(total=len(memories), scopes=scope_summaries)

    @staticmethod
    def _to_listing(memory: Memory) -> MemoryListing:
        if memory.id is None:
            raise ValueError("Cannot list a memory that has no id.")
        return MemoryListing(
            id=memory.id,
            overview=memory.overview,
            tags=list(memory.tags),
            scope=memory.scope,
            content_length=len(memory.content) if memory.content is not None else 0,
            created_at=memory.created_at,
            created_by=memory.created_by,
        )
