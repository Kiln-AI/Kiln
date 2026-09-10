from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, Query
from kiln_ai.datamodel import Memory
from kiln_ai.datamodel.memory import (
    MAX_CONTENT_LENGTH,
    MAX_OVERVIEW_LENGTH,
    MAX_SCOPE_LENGTH,
)
from kiln_ai.memory import (
    InvalidContentMatchError,
    MemoryListResult,
    MemoryNotFoundError,
    MemoryStore,
    MemorySummary,
)
from pydantic import BaseModel, Field, ValidationError

from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT

_PROJECT_ID_DESC = "The unique identifier of the project."
_MEMORY_ID_DESC = "The unique identifier of the memory."
_SCOPE_DESC = (
    "Opaque scope string. Conventions: 'project' for project-wide knowledge; "
    "'task::<task_id>' for task-scoped work. Not validated against existing records."
)
_TAGS_DESC = "Snake_case tags (no spaces) for filtering."


def _store(project_id: str) -> MemoryStore:
    return MemoryStore(project_from_id(project_id))


def _validation_error(exc: ValidationError) -> HTTPException:
    message = "; ".join(e.get("msg", "") for e in exc.errors()) or str(exc)
    return HTTPException(status_code=422, detail=message)


class SaveMemoryRequest(BaseModel):
    """Body for creating a memory. `scope` is required — there is no default."""

    overview: str = Field(
        max_length=MAX_OVERVIEW_LENGTH,
        description="One-line summary written so a future reader can decide whether "
        "to fetch the content. For very short memories this IS the whole memory "
        "(leave content null). No newlines.",
    )
    scope: str = Field(max_length=MAX_SCOPE_LENGTH, description=_SCOPE_DESC)
    content: str | None = Field(
        default=None,
        max_length=MAX_CONTENT_LENGTH,
        description="The memory body: the finding/fact/decision with its conditions "
        "and evidence level. Null when the overview says everything.",
    )
    tags: list[str] = Field(default_factory=list, description=_TAGS_DESC)


class UpdateMemoryRequest(BaseModel):
    """Body for updating a memory. Only provided fields are changed; an explicit
    null clears `content`. Omitted fields are left untouched."""

    overview: str | None = Field(
        default=None,
        max_length=MAX_OVERVIEW_LENGTH,
        description="New one-line summary. No newlines.",
    )
    content: str | None = Field(
        default=None,
        max_length=MAX_CONTENT_LENGTH,
        description="New memory body. Empty or null clears it.",
    )
    tags: list[str] | None = Field(default=None, description=_TAGS_DESC)
    scope: str | None = Field(
        default=None, max_length=MAX_SCOPE_LENGTH, description=_SCOPE_DESC
    )


def connect_memory_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/memories",
        summary="Save Memory",
        tags=["Memory"],
        openapi_extra=ALLOW_AGENT,
    )
    async def save_memory(
        project_id: Annotated[str, Path(description=_PROJECT_ID_DESC)],
        body: SaveMemoryRequest,
    ) -> Memory:
        try:
            return _store(project_id).save_memory(
                overview=body.overview,
                scope=body.scope,
                content=body.content,
                tags=body.tags,
            )
        except ValidationError as e:
            raise _validation_error(e)

    @app.get(
        "/api/projects/{project_id}/memories",
        summary="List Memories",
        tags=["Memory"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_memories(
        project_id: Annotated[str, Path(description=_PROJECT_ID_DESC)],
        scope: Annotated[
            str | None,
            Query(description="Exact-match scope filter. Omit for all scopes."),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Query(
                description="Memory must have ALL of these tags (AND). Repeat the "
                "param for multiple tags; omit for no tag filter."
            ),
        ] = None,
        content_match: Annotated[
            str | None,
            Query(description="Case-insensitive regex over overview + content."),
        ] = None,
        limit: Annotated[int, Query(ge=1, description="Max rows to return.")] = 50,
        offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
    ) -> MemoryListResult:
        """List memory summaries newest-first. content_length 0 means the overview
        is the whole memory. Truncation fields nudge how to narrow the results."""
        try:
            return _store(project_id).list_memories(
                scope=scope,
                tags=tags,
                content_match=content_match,
                limit=limit,
                offset=offset,
            )
        except InvalidContentMatchError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @app.get(
        "/api/projects/{project_id}/memories/summary",
        summary="Memory Summary",
        tags=["Memory"],
        openapi_extra=ALLOW_AGENT,
        response_model_exclude_none=True,
    )
    async def memory_summary(
        project_id: Annotated[str, Path(description=_PROJECT_ID_DESC)],
        scope: Annotated[
            str | None,
            Query(description="Limit to one scope. Omit for all scopes."),
        ] = None,
    ) -> MemorySummary:
        """Cheap per-scope orientation (counts, newest timestamp, tag cardinalities)
        with no record content. Call before targeted list queries."""
        return _store(project_id).memory_summary(scope=scope)

    @app.get(
        "/api/projects/{project_id}/memories/by_ids",
        summary="Get Memories",
        tags=["Memory"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_memories(
        project_id: Annotated[str, Path(description=_PROJECT_ID_DESC)],
        ids: Annotated[list[str], Query(description="The memory ids to fetch.")],
    ) -> list[Memory]:
        """Fetch full memory records by id. Unknown ids are omitted from the result."""
        return _store(project_id).get_memories(ids)

    @app.patch(
        "/api/projects/{project_id}/memories/{memory_id}",
        summary="Update Memory",
        tags=["Memory"],
        openapi_extra=ALLOW_AGENT,
    )
    async def update_memory(
        project_id: Annotated[str, Path(description=_PROJECT_ID_DESC)],
        memory_id: Annotated[str, Path(description=_MEMORY_ID_DESC)],
        body: UpdateMemoryRequest,
    ) -> Memory:
        # Only forward fields the caller actually provided, so omitted fields are
        # left untouched while an explicit null clears content.
        updates: dict[str, Any] = {
            field: getattr(body, field)
            for field in ("overview", "content", "tags", "scope")
            if field in body.model_fields_set
        }
        try:
            return _store(project_id).update_memory(memory_id, **updates)
        except MemoryNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValidationError as e:
            raise _validation_error(e)

    @app.delete(
        "/api/projects/{project_id}/memories/{memory_id}",
        summary="Delete Memory",
        tags=["Memory"],
        openapi_extra=ALLOW_AGENT,
    )
    async def delete_memory(
        project_id: Annotated[str, Path(description=_PROJECT_ID_DESC)],
        memory_id: Annotated[str, Path(description=_MEMORY_ID_DESC)],
    ) -> None:
        """Hard-delete a memory. For junk, wrong, or obsolete memories; use update
        instead if the memory should be corrected rather than removed."""
        try:
            _store(project_id).delete_memory(memory_id)
        except MemoryNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
