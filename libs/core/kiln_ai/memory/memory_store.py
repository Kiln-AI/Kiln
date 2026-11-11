from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime
from typing import Any

import regex
from pydantic import BaseModel, Field

from kiln_ai.datamodel.basemodel import KilnParentModel
from kiln_ai.datamodel.memory import Memory
from kiln_ai.datamodel.model_cache import ModelCache

logger = logging.getLogger(__name__)

# The CPU time that the content_match regex can use in one list_memories call,
# over all records together. The regex module counts its timeout in process CPU
# time, so the deadline uses the same clock (time.process_time).
CONTENT_MATCH_TIME_BUDGET_SECONDS = 0.25


class MemoryNotFoundError(ValueError):
    """Raised when an update/delete targets an id that is not in the store."""

    def __init__(self, memory_id: str):
        self.memory_id = memory_id
        super().__init__(f"No memory with id '{memory_id}' in this store.")


class InvalidContentMatchError(ValueError):
    """Raised when list_memories is called with an invalid content_match regex."""

    def __init__(self, message: str):
        super().__init__(f"Invalid content_match regex: {message}")


class ContentMatchTooExpensiveError(ValueError):
    """Raised when the content_match regex does not finish inside the time budget.

    A pattern with nested quantifiers can backtrack for an exponential time. The
    regex engine holds the GIL while it runs, so without a limit one request
    stops every other request of the server.
    """

    def __init__(self):
        super().__init__(
            "content_match is too expensive to evaluate; simplify the pattern."
        )


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
    matched: int = Field(
        description="How many memories matched the filters, across all pages."
    )
    remaining: int = Field(
        description="How many matching memories come after this page."
    )
    remaining_tag_counts: dict[str, int]


class ScopeSummary(BaseModel):
    """Counts for the memories of one scope: how many, the newest, and per-tag counts."""

    scope: str
    count: int
    newest: datetime
    tags: dict[str, int]
    untagged: int | None = Field(
        default=None,
        description="How many memories in this scope have no tags. Null when none.",
    )


class MemorySummary(BaseModel):
    """An orientation view of a memory store, with no record content: the total and
    one ScopeSummary per scope, newest scope first."""

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
        # One unreadable file (corrupt JSON, a row over a length cap, a file from a
        # newer Kiln) must not break listing for the whole project. Skip it and log it.
        memories, errors = self.memory_model.all_children_of_parent_path_with_errors(
            self.parent.path, readonly=True
        )
        for error in errors:
            logger.warning(
                "Skipping unreadable memory file %s: %s", error.path, error.message
            )
        return memories

    def _find(self, ids: set[str]) -> dict[str, Memory]:
        # The base-class id lookups raise on the first sibling they cannot load, so
        # one bad file (or one deleted by another process mid-scan) would break
        # every lookup by id. Skip such files here, the same as _all does.
        found: dict[str, Memory] = {}
        cache = ModelCache.shared()
        for path in self.memory_model.iterate_children_paths_of_parent_path(
            self.parent.path
        ):
            cached_id = cache.get_model_id(path, self.memory_model)
            if cached_id is not None and cached_id not in ids:
                continue
            try:
                memory = self.memory_model.load_from_file(path, readonly=True)
                if memory.id in ids:
                    found[memory.id] = self.memory_model.load_from_file(path)
            except Exception as e:
                logger.warning("Skipping unreadable memory file %s: %s", path, e)
        return found

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
        return list(self._find(set(ids)).values())

    def update_memory(
        self,
        memory_id: str,
        *,
        overview: Any = _UNSET,
        content: Any = _UNSET,
        tags: Any = _UNSET,
        scope: Any = _UNSET,
    ) -> Memory:
        memory = self._find({memory_id}).get(memory_id)
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
        # An update must not bring back a memory that another process deleted.
        # The check fails fast; create_dirs=False covers a delete that lands
        # after it, because the write then finds no folder to write into.
        if memory.path is None or not memory.path.is_file():
            raise MemoryNotFoundError(memory_id)
        try:
            memory.save_to_file(create_dirs=False)
        except FileNotFoundError:
            raise MemoryNotFoundError(memory_id)
        return memory

    def delete_memory(self, memory_id: str) -> None:
        memory = self._find({memory_id}).get(memory_id)
        if memory is None:
            raise MemoryNotFoundError(memory_id)
        try:
            memory.delete()
        except FileNotFoundError:
            # Another process deleted it after the lookup.
            raise MemoryNotFoundError(memory_id)

    def list_memories(
        self,
        *,
        scope: str | None = None,
        tags: list[str] | None = None,
        content_match: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MemoryListResult:
        # Negative values would silently become Python's negative-index slicing,
        # returning a surprising page and a wrong remaining count.
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if offset < 0:
            raise ValueError("offset cannot be negative")

        memories = self._all()

        if scope is not None:
            memories = [m for m in memories if m.scope == scope]
        if tags:
            wanted = set(tags)
            memories = [m for m in memories if wanted.issubset(set(m.tags))]
        if content_match is not None:
            memories = self._filter_by_content_match(memories, content_match)

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

    @staticmethod
    def _filter_by_content_match(
        memories: list[Memory], content_match: str
    ) -> list[Memory]:
        try:
            # The regex package exports its flags through star imports that ty
            # cannot follow.
            flags = regex.IGNORECASE  # type: ignore[unresolved-attribute]
            pattern = regex.compile(content_match, flags)
        except regex.error as e:
            raise InvalidContentMatchError(str(e))

        # One deadline for the full call, not one for each record. Many records
        # that are each slow must not add up to a long stop of the server.
        deadline = time.process_time() + CONTENT_MATCH_TIME_BUDGET_SECONDS

        def matches(text: str) -> bool:
            remaining = deadline - time.process_time()
            if remaining <= 0:
                raise ContentMatchTooExpensiveError()
            try:
                return pattern.search(text, timeout=remaining) is not None
            except TimeoutError:
                raise ContentMatchTooExpensiveError()

        return [
            m
            for m in memories
            if matches(m.overview) or (m.content is not None and matches(m.content))
        ]

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
