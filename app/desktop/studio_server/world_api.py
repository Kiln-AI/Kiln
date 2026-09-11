"""World API — CRUD for worlds, and discovery of the tools their OpenEnv
environments serve.

A world points at a running OpenEnv environment by URL; Kiln never starts or stops one.
This API records the pointer and can ask the environment what tools it serves, so run
configs can list them.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel.tool_id import build_world_tool_id
from kiln_ai.datamodel.world import World
from kiln_ai.worlds.session_manager import OpenEnvError, shared_session_manager
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


class WorldCreateRequest(BaseModel):
    name: str
    description: str | None = None
    env_url: str | None = None


class WorldUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    env_url: str | None = None


class WorldResponse(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    env_url: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None


class WorldToolResponse(BaseModel):
    tool_id: str = Field(
        description="The id a run config uses to list this tool directly: kiln_tool::world::<world_id>::<tool_name>."
    )
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


def _world_from_id(project_id: str, world_id: str) -> World:
    project = project_from_id(project_id)
    world = World.from_id_and_parent_path(world_id, project.path)
    if world is None:
        raise HTTPException(status_code=404, detail="World not found")
    return world


def _world_response(world: World) -> WorldResponse:
    return WorldResponse(
        id=world.id,
        name=world.name,
        description=world.description,
        env_url=world.env_url,
        created_at=world.created_at,
        created_by=world.created_by,
    )


def connect_world_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/worlds",
        summary="Create World",
        tags=["Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_world(
        project_id: Annotated[str, Path(description="The project id.")],
        request: WorldCreateRequest,
    ) -> WorldResponse:
        project = project_from_id(project_id)
        try:
            world = World(
                name=request.name,
                description=request.description,
                env_url=request.env_url,
                parent=project,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        world.save_to_file()
        return _world_response(world)

    @app.get(
        "/api/projects/{project_id}/worlds",
        summary="List Worlds",
        tags=["Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_worlds(
        project_id: Annotated[str, Path(description="The project id.")],
    ) -> list[WorldResponse]:
        project = project_from_id(project_id)
        worlds = project.worlds(readonly=True)
        worlds.sort(key=lambda w: w.created_at or datetime.min)
        return [_world_response(w) for w in worlds]

    @app.get(
        "/api/projects/{project_id}/worlds/{world_id}",
        summary="Get World",
        tags=["Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_world(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The world id.")],
    ) -> WorldResponse:
        return _world_response(_world_from_id(project_id, world_id))

    @app.patch(
        "/api/projects/{project_id}/worlds/{world_id}",
        summary="Update World",
        tags=["Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def update_world(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The world id.")],
        request: WorldUpdateRequest,
    ) -> WorldResponse:
        world = _world_from_id(project_id, world_id)
        try:
            for field, value in request.model_dump(exclude_unset=True).items():
                setattr(world, field, value)
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        world.save_to_file()
        return _world_response(world)

    @app.delete(
        "/api/projects/{project_id}/worlds/{world_id}",
        summary="Delete World",
        tags=["Worlds"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to delete a world, including its environment folder?"
        ),
    )
    async def delete_world(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The world id.")],
    ) -> None:
        _world_from_id(project_id, world_id).delete()

    @app.get(
        "/api/projects/{project_id}/worlds/{world_id}/tools",
        summary="List World Tools",
        description="The tools the world's OpenEnv environment serves, read from the running server at env_url.",
        tags=["Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_world_tools(
        project_id: Annotated[str, Path(description="The project id.")],
        world_id: Annotated[str, Path(description="The world id.")],
    ) -> list[WorldToolResponse]:
        world = _world_from_id(project_id, world_id)
        if not world.env_url:
            raise HTTPException(
                status_code=400,
                detail=f"World '{world.name}' has no env_url. Kiln does not "
                "start environments: run the OpenEnv server and set env_url.",
            )
        try:
            tools = await shared_session_manager().list_tools(world)
        except (OpenEnvError, ValueError) as e:
            raise HTTPException(status_code=502, detail=str(e))
        return [
            WorldToolResponse(
                tool_id=build_world_tool_id(world.id, tool.name),
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools
        ]
