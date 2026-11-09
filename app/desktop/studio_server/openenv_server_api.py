"""OpenEnv server API — CRUD for OpenEnv servers, and discovery of the tools they
serve.

Kiln's OpenEnv server record points at a running OpenEnv server by URL; Kiln never
starts or stops one. This API records the pointer and can ask the server what tools it
serves, so run configs can list them.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.openenv import NamedResetKwargs, OpenEnvServer
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.openenv.session_manager import OpenEnvError, shared_session_manager
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


_NAME_DESCRIPTION = "User-facing display name."
_DESCRIPTION_DESCRIPTION = "User-facing notes about the OpenEnv server."
_URL_DESCRIPTION = (
    "Base URL of an OpenEnv server that is already running (e.g. "
    "http://127.0.0.1:8000). Kiln connects to it; it never starts one. Evals run in "
    "this OpenEnv server send their tool calls to it."
)
_NAMED_RESET_KWARGS_DESCRIPTION = (
    "Named reset kwargs a run can start the environment with, in order. The first is "
    "the default. Names must be unique."
)
_URL_ERROR = (
    "Enter a full URL starting with http:// or https://, like http://127.0.0.1:8004."
)
_RESET_KWARGS_NOT_OBJECT_ERROR = "Reset arguments must be a JSON object."


class NamedResetKwargsRequest(BaseModel):
    """Reset kwargs saved under a name, shown in the UI as an Environment Option."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="User-facing name, unique within the environment.")
    # Any JSON is accepted here so a non-object gets the friendly 400 from the
    # handler instead of FastAPI's generic 422; OpenEnv enforces the object type.
    reset_kwargs: JsonValue = Field(
        default_factory=dict,
        description="Keyword arguments for the environment's reset(), as a JSON object.",
    )


class OpenEnvServerCreateRequest(BaseModel):
    """A new OpenEnv server: Kiln's saved pointer to a running OpenEnv environment."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    url: str | None = Field(default=None, description=_URL_DESCRIPTION)
    named_reset_kwargs: list[NamedResetKwargsRequest] = Field(
        default_factory=list, description=_NAMED_RESET_KWARGS_DESCRIPTION
    )


class OpenEnvServerUpdateRequest(BaseModel):
    """Changes to an OpenEnv server. Only the fields sent are changed, and
    `named_reset_kwargs`, when sent, replaces the whole list."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString | None = Field(default=None, description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    url: str | None = Field(default=None, description=_URL_DESCRIPTION)
    named_reset_kwargs: list[NamedResetKwargsRequest] | None = Field(
        default=None, description=_NAMED_RESET_KWARGS_DESCRIPTION
    )


class OpenEnvServerResponse(BaseModel):
    """An OpenEnv server: Kiln's saved pointer to a running OpenEnv environment."""

    id: str | None = Field(default=None, description="The OpenEnv server's id.")
    name: str = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    url: str | None = Field(default=None, description=_URL_DESCRIPTION)
    named_reset_kwargs: list[NamedResetKwargs] = Field(
        default_factory=list, description=_NAMED_RESET_KWARGS_DESCRIPTION
    )
    created_at: datetime | None = Field(
        default=None, description="When the OpenEnv server was created."
    )
    created_by: str | None = Field(
        default=None, description="Who created the OpenEnv server."
    )


class OpenEnvToolResponse(BaseModel):
    """One tool the OpenEnv server's environment serves."""

    tool_id: str = Field(
        description="The id a run config uses to list this tool directly: kiln_tool::openenv::<openenv_server_id>::<tool_name>."
    )
    name: str = Field(description="The tool's function name, as the model sees it.")
    description: str = Field(
        default="", description="The tool's description, as the model sees it."
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON schema of the tool's arguments."
    )


def _openenv_server_from_id(project_id: str, openenv_server_id: str) -> OpenEnvServer:
    project = project_from_id(project_id)
    openenv_server = OpenEnvServer.from_id_and_parent_path(
        openenv_server_id, project.path
    )
    if openenv_server is None:
        raise HTTPException(status_code=404, detail="OpenEnv server not found")
    return openenv_server


def _openenv_server_response(openenv_server: OpenEnvServer) -> OpenEnvServerResponse:
    return OpenEnvServerResponse(
        id=openenv_server.id,
        name=openenv_server.name,
        description=openenv_server.description,
        url=openenv_server.url,
        named_reset_kwargs=openenv_server.named_reset_kwargs,
        created_at=openenv_server.created_at,
        created_by=openenv_server.created_by,
    )


def _friendly_error(error: PydanticValidationError) -> str:
    """The first validation error, in the words the UI shows the user."""
    first = error.errors()[0]
    loc = first["loc"]
    if loc[:1] == ("url",):
        return _URL_ERROR
    if (
        loc[:1] == ("named_reset_kwargs",)
        and loc[-1:] == ("reset_kwargs",)
        and first["type"] == "dict_type"
    ):
        return _RESET_KWARGS_NOT_OBJECT_ERROR
    if first["type"] == "value_error":
        return str(first["ctx"]["error"])
    return str(error)


def connect_openenv_server_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/openenv_servers",
        summary="Create OpenEnv Server",
        tags=["OpenEnv Servers"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to create an OpenEnv server? Evals run in it will send their data to its URL."
        ),
    )
    async def create_openenv_server(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        request: OpenEnvServerCreateRequest,
    ) -> OpenEnvServerResponse:
        project = project_from_id(project_id)
        try:
            openenv_server = OpenEnvServer(
                name=request.name,
                description=request.description,
                url=request.url,
                named_reset_kwargs=[
                    option.model_dump() for option in request.named_reset_kwargs
                ],
                parent=project,
            )
        except PydanticValidationError as e:
            raise HTTPException(status_code=400, detail=_friendly_error(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        openenv_server.save_to_file()
        return _openenv_server_response(openenv_server)

    @app.get(
        "/api/projects/{project_id}/openenv_servers",
        summary="List OpenEnv Servers",
        tags=["OpenEnv Servers"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_openenv_servers(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> list[OpenEnvServerResponse]:
        project = project_from_id(project_id)
        openenv_servers = project.openenv_servers(readonly=True)
        openenv_servers.sort(
            key=lambda openenv_server: openenv_server.created_at or datetime.min
        )
        return [
            _openenv_server_response(openenv_server)
            for openenv_server in openenv_servers
        ]

    @app.get(
        "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
        summary="Get OpenEnv Server",
        tags=["OpenEnv Servers"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_openenv_server(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_server_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv server.")
        ],
    ) -> OpenEnvServerResponse:
        return _openenv_server_response(
            _openenv_server_from_id(project_id, openenv_server_id)
        )

    @app.patch(
        "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
        summary="Update OpenEnv Server",
        tags=["OpenEnv Servers"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to update an OpenEnv server? Changing its URL changes where evals run in it send their data."
        ),
    )
    async def update_openenv_server(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_server_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv server.")
        ],
        request: OpenEnvServerUpdateRequest,
    ) -> OpenEnvServerResponse:
        openenv_server = _openenv_server_from_id(project_id, openenv_server_id)
        try:
            for field, value in request.model_dump(exclude_unset=True).items():
                setattr(openenv_server, field, value)
        except PydanticValidationError as e:
            raise HTTPException(status_code=400, detail=_friendly_error(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        openenv_server.save_to_file()
        return _openenv_server_response(openenv_server)

    @app.delete(
        "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
        summary="Delete OpenEnv Server",
        tags=["OpenEnv Servers"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to delete an OpenEnv server?"
        ),
    )
    async def delete_openenv_server(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_server_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv server.")
        ],
    ) -> None:
        """Delete an OpenEnv server, if no saved eval input still resets into it.

        409 when one does. An eval input names its OpenEnv server by id, so a delete
        that went through would leave every eval run on it failing to resolve the
        OpenEnv server. Traces made on the server keep their own copy of the episode,
        and stay readable.
        """
        project = project_from_id(project_id)
        openenv_server = _openenv_server_from_id(project_id, openenv_server_id)
        referencing = sum(
            1
            for task in project.tasks(readonly=True)
            for eval_input in task.eval_inputs(readonly=True)
            if eval_input.openenv_reset is not None
            and eval_input.openenv_reset.openenv_server_id == openenv_server.id
        )
        if referencing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"OpenEnv server is still used by {referencing} eval input(s), which reset "
                    "into it by id. Deleting it would leave evals on those inputs "
                    "unable to run. Remove or change those inputs first."
                ),
            )
        openenv_server.delete()

    @app.get(
        "/api/projects/{project_id}/openenv_servers/{openenv_server_id}/tools",
        summary="List OpenEnv Server Tools",
        description="The tools the OpenEnv server's environment serves, read fresh from the running server at url.",
        tags=["OpenEnv Servers"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_openenv_server_tools(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        openenv_server_id: Annotated[
            str, Path(description="The unique identifier of the OpenEnv server.")
        ],
    ) -> list[OpenEnvToolResponse]:
        openenv_server = _openenv_server_from_id(project_id, openenv_server_id)
        if not openenv_server.url:
            raise HTTPException(
                status_code=400,
                detail=f"OpenEnv server '{openenv_server.name}' has no url. Kiln does not "
                "start environments: run the OpenEnv server and set url.",
            )
        try:
            tools = await shared_session_manager().list_tools(
                openenv_server, fresh=True
            )
        except (OpenEnvError, ValueError) as e:
            raise HTTPException(status_code=502, detail=str(e))
        return [
            OpenEnvToolResponse(
                tool_id=build_openenv_tool_id(openenv_server.id, tool.name),
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools
        ]
