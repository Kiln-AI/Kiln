"""Synthetic World API — CRUD for worlds, their synthetic tools, and their fixtures.

No UI consumes this yet; it exists so worlds can be authored by scripts and agents
through the same server the rest of Kiln uses. Dedicated response models throughout:
`SyntheticTool` inherits `CodeTool`'s wrap-serializer, whose serialization-mode JSON
schema is untyped, so it must not be a FastAPI response model directly.
"""

import logging
from datetime import datetime
from pathlib import Path as FilePath
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Path, UploadFile
from kiln_ai.adapters.eval.v2_eval_code_eval import has_add_code_trust
from kiln_ai.datamodel.synthetic_world import (
    SyntheticFixture,
    SyntheticTool,
    SyntheticWorld,
)
from kiln_ai.datamodel.tool_id import ToolId
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


class SyntheticWorldCreateRequest(BaseModel):
    name: str
    description: str | None = None
    strict: bool = False
    framework_content_hash: str | None = None


class SyntheticWorldUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    strict: bool | None = None
    framework_content_hash: str | None = None


class SyntheticWorldResponse(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    strict: bool = False
    framework_content_hash: str | None = None
    tool_count: int = 0
    fixture_count: int = 0
    created_at: datetime | None = None
    created_by: str | None = None


class SyntheticToolCreateRequest(BaseModel):
    name: str
    description: str | None = None
    replaces_tool_id: ToolId
    tool_function_name: str
    tool_description: str = Field(min_length=1)
    parameters_schema: dict[str, Any]
    code: str
    timeout_seconds: int = Field(default=60, ge=1)
    tool_allowlist: list[ToolId] = Field(default_factory=list)


class SyntheticToolUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class SyntheticToolResponse(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    replaces_tool_id: str
    tool_function_name: str
    tool_description: str
    parameters_schema: dict[str, Any]
    code: str
    timeout_seconds: int
    tool_allowlist: list[ToolId] = Field(default_factory=list)
    created_at: datetime | None = None
    created_by: str | None = None


class SyntheticToolCreateResponse(SyntheticToolResponse):
    not_trusted: bool = False


class SyntheticFixtureCreateRequest(BaseModel):
    name: str
    description: str | None = None
    frozen_time: datetime | None = None


class SyntheticFixtureResponse(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    frozen_time: datetime | None = None
    data_files: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    created_by: str | None = None


class SyntheticWorldValidationResponse(BaseModel):
    warnings: list[str] = Field(default_factory=list)


def _world_from_id(project_id: str, world_id: str) -> SyntheticWorld:
    project = project_from_id(project_id)
    world = SyntheticWorld.from_id_and_parent_path(world_id, project.path)
    if world is None:
        raise HTTPException(status_code=404, detail="Synthetic world not found")
    return world


def _tool_from_id(world: SyntheticWorld, tool_id: str) -> SyntheticTool:
    tool = SyntheticTool.from_id_and_parent_path(tool_id, world.path)
    if tool is None:
        raise HTTPException(status_code=404, detail="Synthetic tool not found")
    return tool


def _fixture_from_id(world: SyntheticWorld, fixture_id: str) -> SyntheticFixture:
    fixture = world.fixture_by_id(fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Synthetic fixture not found")
    return fixture


def _world_response(world: SyntheticWorld) -> SyntheticWorldResponse:
    return SyntheticWorldResponse(
        id=world.id,
        name=world.name,
        description=world.description,
        strict=world.strict,
        framework_content_hash=world.framework_content_hash,
        tool_count=len(world.tools(readonly=True)),
        fixture_count=len(world.fixtures(readonly=True)),
        created_at=world.created_at,
        created_by=world.created_by,
    )


def _tool_response(tool: SyntheticTool) -> SyntheticToolResponse:
    return SyntheticToolResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        replaces_tool_id=tool.replaces_tool_id,
        tool_function_name=tool.tool_function_name,
        tool_description=tool.tool_description,
        parameters_schema=tool.parameters_schema,
        code=tool.code,
        timeout_seconds=tool.timeout_seconds,
        tool_allowlist=tool.tool_allowlist,
        created_at=tool.created_at,
        created_by=tool.created_by,
    )


def _fixture_response(fixture: SyntheticFixture) -> SyntheticFixtureResponse:
    data_dir = fixture.data_dir()
    files = (
        sorted(
            p.relative_to(data_dir).as_posix()
            for p in data_dir.rglob("*")
            if p.is_file()
        )
        if data_dir.is_dir()
        else []
    )
    return SyntheticFixtureResponse(
        id=fixture.id,
        name=fixture.name,
        description=fixture.description,
        frozen_time=fixture.frozen_time,
        data_files=files,
        created_at=fixture.created_at,
        created_by=fixture.created_by,
    )


def _safe_upload_name(filename: str | None) -> str:
    """A bare filename for an uploaded fixture file: no directories, no traversal."""
    name = FilePath(filename or "").name
    if not name or name in (".", "..") or name.startswith("."):
        raise HTTPException(
            status_code=400, detail=f"Invalid fixture file name: {filename!r}"
        )
    return name


def connect_synthetic_world_api(app: FastAPI):
    # ---- worlds ----

    @app.post(
        "/api/projects/{project_id}/synthetic_worlds",
        summary="Create Synthetic World",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_synthetic_world(
        project_id: Annotated[str, Path(description="The project id.")],
        request: SyntheticWorldCreateRequest,
    ) -> SyntheticWorldResponse:
        project = project_from_id(project_id)
        try:
            world = SyntheticWorld(
                name=request.name,
                description=request.description,
                strict=request.strict,
                framework_content_hash=request.framework_content_hash,
                parent=project,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        world.save_to_file()
        world.lib_dir().mkdir(exist_ok=True)
        return _world_response(world)

    @app.get(
        "/api/projects/{project_id}/synthetic_worlds",
        summary="List Synthetic Worlds",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_synthetic_worlds(
        project_id: Annotated[str, Path(description="The project id.")],
    ) -> list[SyntheticWorldResponse]:
        project = project_from_id(project_id)
        worlds = project.synthetic_worlds(readonly=True)
        worlds.sort(key=lambda w: w.created_at or datetime.min)
        return [_world_response(w) for w in worlds]

    @app.get(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}",
        summary="Get Synthetic World",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_synthetic_world(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
    ) -> SyntheticWorldResponse:
        return _world_response(_world_from_id(project_id, world_id))

    @app.patch(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}",
        summary="Update Synthetic World",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def update_synthetic_world(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
        request: SyntheticWorldUpdateRequest,
    ) -> SyntheticWorldResponse:
        world = _world_from_id(project_id, world_id)
        try:
            for field, value in request.model_dump(exclude_unset=True).items():
                setattr(world, field, value)
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        world.save_to_file()
        return _world_response(world)

    @app.delete(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}",
        summary="Delete Synthetic World",
        tags=["Synthetic Worlds"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to delete a synthetic world, including its tools and fixtures?"
        ),
    )
    async def delete_synthetic_world(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
    ) -> None:
        _world_from_id(project_id, world_id).delete()

    @app.get(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/validate",
        summary="Validate Synthetic World Bindings",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def validate_synthetic_world(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
    ) -> SyntheticWorldValidationResponse:
        project = project_from_id(project_id)
        world = _world_from_id(project_id, world_id)
        try:
            warnings = world.validate_bindings(project)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return SyntheticWorldValidationResponse(warnings=warnings)

    # ---- tools ----

    @app.post(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/tools",
        summary="Create Synthetic Tool",
        tags=["Synthetic Worlds"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to save a synthetic tool (Python that runs on your machine during evals)?"
        ),
    )
    async def create_synthetic_tool(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
        request: SyntheticToolCreateRequest,
    ) -> SyntheticToolCreateResponse:
        project = project_from_id(project_id)
        world = _world_from_id(project_id, world_id)
        if not has_add_code_trust(str(project.path)):
            return SyntheticToolCreateResponse(
                name=request.name,
                replaces_tool_id=request.replaces_tool_id,
                tool_function_name=request.tool_function_name,
                tool_description=request.tool_description,
                parameters_schema=request.parameters_schema,
                code=request.code,
                timeout_seconds=request.timeout_seconds,
                not_trusted=True,
            )
        if world.binding_for(request.replaces_tool_id) is not None:
            raise HTTPException(
                status_code=400,
                detail=f"World already replaces {request.replaces_tool_id}",
            )
        try:
            tool = SyntheticTool(
                name=request.name,
                description=request.description,
                replaces_tool_id=request.replaces_tool_id,
                tool_function_name=request.tool_function_name,
                tool_description=request.tool_description,
                parameters_schema=request.parameters_schema,
                code=request.code,
                timeout_seconds=request.timeout_seconds,
                tool_allowlist=request.tool_allowlist,
                parent=world,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        tool.save_to_file()
        return SyntheticToolCreateResponse(**_tool_response(tool).model_dump())

    @app.get(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/tools",
        summary="List Synthetic Tools",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_synthetic_tools(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
    ) -> list[SyntheticToolResponse]:
        world = _world_from_id(project_id, world_id)
        tools = world.tools(readonly=True)
        tools.sort(key=lambda t: t.created_at or datetime.min)
        return [_tool_response(t) for t in tools]

    @app.patch(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/tools/{tool_id}",
        summary="Update Synthetic Tool",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def update_synthetic_tool(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
        tool_id: Annotated[str, Path(description="The synthetic tool id.")],
        request: SyntheticToolUpdateRequest,
    ) -> SyntheticToolResponse:
        tool = _tool_from_id(_world_from_id(project_id, world_id), tool_id)
        try:
            for field, value in request.model_dump(exclude_unset=True).items():
                setattr(tool, field, value)
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        tool.save_to_file()
        return _tool_response(tool)

    @app.delete(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/tools/{tool_id}",
        summary="Delete Synthetic Tool",
        tags=["Synthetic Worlds"],
        openapi_extra=DENY_AGENT,
    )
    async def delete_synthetic_tool(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
        tool_id: Annotated[str, Path(description="The synthetic tool id.")],
    ) -> None:
        _tool_from_id(_world_from_id(project_id, world_id), tool_id).delete()

    # ---- fixtures ----

    @app.post(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/fixtures",
        summary="Create Synthetic Fixture",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_synthetic_fixture(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
        request: SyntheticFixtureCreateRequest,
    ) -> SyntheticFixtureResponse:
        world = _world_from_id(project_id, world_id)
        try:
            fixture = SyntheticFixture(
                name=request.name,
                description=request.description,
                frozen_time=request.frozen_time,
                parent=world,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        fixture.save_to_file()
        fixture.data_dir().mkdir(exist_ok=True)
        return _fixture_response(fixture)

    @app.post(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/fixtures/{fixture_id}/data",
        summary="Upload Synthetic Fixture Data File",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def upload_synthetic_fixture_data(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
        fixture_id: Annotated[str, Path(description="The synthetic fixture id.")],
        file: Annotated[UploadFile, File(description="The data file to add.")],
    ) -> SyntheticFixtureResponse:
        fixture = _fixture_from_id(_world_from_id(project_id, world_id), fixture_id)
        name = _safe_upload_name(file.filename)
        data_dir = fixture.data_dir()
        data_dir.mkdir(exist_ok=True)
        target = data_dir / name
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        return _fixture_response(fixture)

    @app.get(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/fixtures",
        summary="List Synthetic Fixtures",
        tags=["Synthetic Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_synthetic_fixtures(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
    ) -> list[SyntheticFixtureResponse]:
        world = _world_from_id(project_id, world_id)
        fixtures = world.fixtures(readonly=True)
        fixtures.sort(key=lambda f: f.created_at or datetime.min)
        return [_fixture_response(f) for f in fixtures]

    @app.delete(
        "/api/projects/{project_id}/synthetic_worlds/{world_id}/fixtures/{fixture_id}",
        summary="Delete Synthetic Fixture",
        tags=["Synthetic Worlds"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to delete a synthetic fixture and its data files?"
        ),
    )
    async def delete_synthetic_fixture(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The synthetic world id.")],
        fixture_id: Annotated[str, Path(description="The synthetic fixture id.")],
    ) -> None:
        _fixture_from_id(_world_from_id(project_id, world_id), fixture_id).delete()
