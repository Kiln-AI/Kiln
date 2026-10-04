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
from kiln_ai.datamodel.basemodel import FilenameString
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


_NAME_DESCRIPTION = "User-facing display name."
_DESCRIPTION_DESCRIPTION = "User-facing notes about the world."
_ENV_URL_DESCRIPTION = (
    "Base URL of an OpenEnv server that is already running (e.g. "
    "http://127.0.0.1:8000). Kiln connects to it; it never starts one. Evals run in "
    "this world send their tool calls to it."
)


class WorldCreateRequest(BaseModel):
    """A new world: a pointer to a running OpenEnv environment."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    env_url: str | None = Field(default=None, description=_ENV_URL_DESCRIPTION)


class WorldUpdateRequest(BaseModel):
    """Changes to a world. Only the fields sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString | None = Field(default=None, description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    env_url: str | None = Field(default=None, description=_ENV_URL_DESCRIPTION)


class WorldResponse(BaseModel):
    """A world: a pointer to a running OpenEnv environment."""

    id: str | None = Field(default=None, description="The world's id.")
    name: str = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    env_url: str | None = Field(default=None, description=_ENV_URL_DESCRIPTION)
    created_at: datetime | None = Field(
        default=None, description="When the world was created."
    )
    created_by: str | None = Field(default=None, description="Who created the world.")


class WorldToolResponse(BaseModel):
    """One tool the world's environment serves."""

    tool_id: str = Field(
        description="The id a run config uses to list this tool directly: kiln_tool::world::<world_id>::<tool_name>."
    )
    name: str = Field(description="The tool's function name, as the model sees it.")
    description: str = Field(
        default="", description="The tool's description, as the model sees it."
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON schema of the tool's arguments."
    )


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
        openapi_extra=agent_policy_require_approval(
            "Allow agent to create a world? Evals run in it will send their data to its environment URL."
        ),
    )
    async def create_world(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
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
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
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
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        world_id: Annotated[
            str, Path(description="The unique identifier of the world.")
        ],
    ) -> WorldResponse:
        return _world_response(_world_from_id(project_id, world_id))

    @app.patch(
        "/api/projects/{project_id}/worlds/{world_id}",
        summary="Update World",
        tags=["Worlds"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to update a world? Changing its environment URL changes where evals run in it send their data."
        ),
    )
    async def update_world(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        world_id: Annotated[
            str, Path(description="The unique identifier of the world.")
        ],
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
        openapi_extra=agent_policy_require_approval("Allow agent to delete a world?"),
    )
    async def delete_world(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        world_id: Annotated[
            str, Path(description="The unique identifier of the world.")
        ],
    ) -> None:
        """Delete a world, if no saved eval input still resets into it.

        409 when one does. An eval input names its world by id, so a delete that went
        through would leave every eval run on it failing to resolve the world.
        Traces made in the world keep their own copy of the episode, and stay readable.
        """
        project = project_from_id(project_id)
        world = _world_from_id(project_id, world_id)
        referencing = sum(
            1
            for task in project.tasks(readonly=True)
            for eval_input in task.eval_inputs(readonly=True)
            if eval_input.world_reset is not None
            and eval_input.world_reset.world_id == world.id
        )
        if referencing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"World is still used by {referencing} eval input(s), which reset "
                    "into it by id. Deleting it would leave evals on those inputs "
                    "unable to run. Remove or change those inputs first."
                ),
            )
        world.delete()

    @app.get(
        "/api/projects/{project_id}/worlds/{world_id}/tools",
        summary="List World Tools",
        description="The tools the world's OpenEnv environment serves, read fresh from the running server at env_url.",
        tags=["Worlds"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_world_tools(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        world_id: Annotated[
            str, Path(description="The unique identifier of the world.")
        ],
    ) -> list[WorldToolResponse]:
        world = _world_from_id(project_id, world_id)
        if not world.env_url:
            raise HTTPException(
                status_code=400,
                detail=f"World '{world.name}' has no env_url. Kiln does not "
                "start environments: run the OpenEnv server and set env_url.",
            )
        try:
            tools = await shared_session_manager().list_tools(world, fresh=True)
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
