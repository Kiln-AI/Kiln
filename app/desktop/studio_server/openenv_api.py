"""OpenEnv API — CRUD for OpenEnvs, and discovery of the tools their OpenEnv
servers serve.

An OpenEnv points at a running OpenEnv server by URL; Kiln never starts or stops one.
This API records the pointer and can ask the server what tools it serves, so run
configs can list them.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.openenv import OpenEnv
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.openenv.session_manager import OpenEnvError, shared_session_manager
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


_NAME_DESCRIPTION = "User-facing display name."
_DESCRIPTION_DESCRIPTION = "User-facing notes about the OpenEnv."
_URL_DESCRIPTION = (
    "Base URL of an OpenEnv server that is already running (e.g. "
    "http://127.0.0.1:8000). Kiln connects to it; it never starts one. Evals run in "
    "this OpenEnv send their tool calls to it."
)


class OpenEnvCreateRequest(BaseModel):
    """A new OpenEnv: Kiln's pointer to a running OpenEnv environment."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    url: str | None = Field(default=None, description=_URL_DESCRIPTION)


class OpenEnvUpdateRequest(BaseModel):
    """Changes to an OpenEnv. Only the fields sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString | None = Field(default=None, description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    url: str | None = Field(default=None, description=_URL_DESCRIPTION)


class OpenEnvResponse(BaseModel):
    """An OpenEnv: Kiln's pointer to a running OpenEnv environment."""

    id: str | None = Field(default=None, description="The OpenEnv's id.")
    name: str = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    url: str | None = Field(default=None, description=_URL_DESCRIPTION)
    created_at: datetime | None = Field(
        default=None, description="When the OpenEnv was created."
    )
    created_by: str | None = Field(default=None, description="Who created the OpenEnv.")


class OpenEnvToolResponse(BaseModel):
    """One tool the OpenEnv's environment serves."""

    tool_id: str = Field(
        description="The id a run config uses to list this tool directly: kiln_tool::openenv::<openenv_id>::<tool_name>."
    )
    name: str = Field(description="The tool's function name, as the model sees it.")
    description: str = Field(
        default="", description="The tool's description, as the model sees it."
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON schema of the tool's arguments."
    )


def _openenv_from_id(project_id: str, openenv_id: str) -> OpenEnv:
    project = project_from_id(project_id)
    openenv = OpenEnv.from_id_and_parent_path(openenv_id, project.path)
    if openenv is None:
        raise HTTPException(status_code=404, detail="OpenEnv not found")
    return openenv


def _openenv_response(openenv: OpenEnv) -> OpenEnvResponse:
    return OpenEnvResponse(
        id=openenv.id,
        name=openenv.name,
        description=openenv.description,
        url=openenv.url,
        created_at=openenv.created_at,
        created_by=openenv.created_by,
    )


def connect_openenv_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/openenvs",
        summary="Create OpenEnv",
        tags=["OpenEnvs"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to create an OpenEnv? Evals run in it will send their data to its URL."
        ),
    )
    async def create_openenv(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        request: OpenEnvCreateRequest,
    ) -> OpenEnvResponse:
        project = project_from_id(project_id)
        try:
            openenv = OpenEnv(
                name=request.name,
                description=request.description,
                url=request.url,
                parent=project,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        openenv.save_to_file()
        return _openenv_response(openenv)

    @app.get(
        "/api/projects/{project_id}/openenvs",
        summary="List OpenEnvs",
        tags=["OpenEnvs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_openenvs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> list[OpenEnvResponse]:
        project = project_from_id(project_id)
        openenvs = project.openenvs(readonly=True)
        openenvs.sort(key=lambda openenv: openenv.created_at or datetime.min)
        return [_openenv_response(openenv) for openenv in openenvs]

    @app.get(
        "/api/projects/{project_id}/openenvs/{openenv_id}",
        summary="Get OpenEnv",
        tags=["OpenEnvs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_openenv(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv.")
        ],
    ) -> OpenEnvResponse:
        return _openenv_response(_openenv_from_id(project_id, openenv_id))

    @app.patch(
        "/api/projects/{project_id}/openenvs/{openenv_id}",
        summary="Update OpenEnv",
        tags=["OpenEnvs"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to update an OpenEnv? Changing its URL changes where evals run in it send their data."
        ),
    )
    async def update_openenv(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv.")
        ],
        request: OpenEnvUpdateRequest,
    ) -> OpenEnvResponse:
        openenv = _openenv_from_id(project_id, openenv_id)
        try:
            for field, value in request.model_dump(exclude_unset=True).items():
                setattr(openenv, field, value)
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        openenv.save_to_file()
        return _openenv_response(openenv)

    @app.delete(
        "/api/projects/{project_id}/openenvs/{openenv_id}",
        summary="Delete OpenEnv",
        tags=["OpenEnvs"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to delete an OpenEnv?"
        ),
    )
    async def delete_openenv(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv.")
        ],
    ) -> None:
        """Delete an OpenEnv, if no saved eval input still resets into it.

        409 when one does. An eval input names its OpenEnv by id, so a delete that went
        through would leave every eval run on it failing to resolve the OpenEnv.
        Traces made in the OpenEnv keep their own copy of the episode, and stay readable.
        """
        project = project_from_id(project_id)
        openenv = _openenv_from_id(project_id, openenv_id)
        referencing = sum(
            1
            for task in project.tasks(readonly=True)
            for eval_input in task.eval_inputs(readonly=True)
            if eval_input.openenv_reset is not None
            and eval_input.openenv_reset.openenv_id == openenv.id
        )
        if referencing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"OpenEnv is still used by {referencing} eval input(s), which reset "
                    "into it by id. Deleting it would leave evals on those inputs "
                    "unable to run. Remove or change those inputs first."
                ),
            )
        openenv.delete()

    @app.get(
        "/api/projects/{project_id}/openenvs/{openenv_id}/tools",
        summary="List OpenEnv Tools",
        description="The tools the OpenEnv environment serves, read fresh from the running server at url.",
        tags=["OpenEnvs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_openenv_tools(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv.")
        ],
    ) -> list[OpenEnvToolResponse]:
        openenv = _openenv_from_id(project_id, openenv_id)
        if not openenv.url:
            raise HTTPException(
                status_code=400,
                detail=f"OpenEnv '{openenv.name}' has no url. Kiln does not "
                "start environments: run the OpenEnv server and set url.",
            )
        try:
            tools = await shared_session_manager().list_tools(openenv, fresh=True)
        except (OpenEnvError, ValueError) as e:
            raise HTTPException(status_code=502, detail=str(e))
        return [
            OpenEnvToolResponse(
                tool_id=build_openenv_tool_id(openenv.id, tool.name),
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools
        ]
