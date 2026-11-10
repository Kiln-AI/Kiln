"""Environment API — CRUD for environments, and discovery of the tools their OpenEnv
servers serve.

An environment points at a running OpenEnv server by URL; Kiln never starts or stops one.
This API records the pointer and can ask the server what tools it serves, so run
configs can list them.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.environment import Environment
from kiln_ai.datamodel.tool_id import build_env_tool_id
from kiln_ai.environments.session_manager import OpenEnvError, shared_session_manager
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


_NAME_DESCRIPTION = "User-facing display name."
_DESCRIPTION_DESCRIPTION = "User-facing notes about the environment."
_ENV_URL_DESCRIPTION = (
    "Base URL of an OpenEnv server that is already running (e.g. "
    "http://127.0.0.1:8000). Kiln connects to it; it never starts one. Evals run in "
    "this environment send their tool calls to it."
)


class EnvironmentCreateRequest(BaseModel):
    """A new environment: a pointer to a running OpenEnv environment."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    env_url: str | None = Field(default=None, description=_ENV_URL_DESCRIPTION)


class EnvironmentUpdateRequest(BaseModel):
    """Changes to an environment. Only the fields sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: FilenameString | None = Field(default=None, description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    env_url: str | None = Field(default=None, description=_ENV_URL_DESCRIPTION)


class EnvironmentResponse(BaseModel):
    """An environment: a pointer to a running OpenEnv environment."""

    id: str | None = Field(default=None, description="The environment's id.")
    name: str = Field(description=_NAME_DESCRIPTION)
    description: str | None = Field(default=None, description=_DESCRIPTION_DESCRIPTION)
    env_url: str | None = Field(default=None, description=_ENV_URL_DESCRIPTION)
    created_at: datetime | None = Field(
        default=None, description="When the environment was created."
    )
    created_by: str | None = Field(
        default=None, description="Who created the environment."
    )


class EnvironmentToolResponse(BaseModel):
    """One tool the environment serves."""

    tool_id: str = Field(
        description="The id a run config uses to list this tool directly: kiln_tool::env::<environment_id>::<tool_name>."
    )
    name: str = Field(description="The tool's function name, as the model sees it.")
    description: str = Field(
        default="", description="The tool's description, as the model sees it."
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON schema of the tool's arguments."
    )


def _env_from_id(project_id: str, environment_id: str) -> Environment:
    project = project_from_id(project_id)
    environment = Environment.from_id_and_parent_path(environment_id, project.path)
    if environment is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return environment


def _env_response(environment: Environment) -> EnvironmentResponse:
    return EnvironmentResponse(
        id=environment.id,
        name=environment.name,
        description=environment.description,
        env_url=environment.env_url,
        created_at=environment.created_at,
        created_by=environment.created_by,
    )


def connect_environment_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/environments",
        summary="Create Environment",
        tags=["Environments"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to create an environment? Evals run in it will send their data to its environment URL."
        ),
    )
    async def create_environment(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        request: EnvironmentCreateRequest,
    ) -> EnvironmentResponse:
        project = project_from_id(project_id)
        try:
            environment = Environment(
                name=request.name,
                description=request.description,
                env_url=request.env_url,
                parent=project,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        environment.save_to_file()
        return _env_response(environment)

    @app.get(
        "/api/projects/{project_id}/environments",
        summary="List Environments",
        tags=["Environments"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_environments(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> list[EnvironmentResponse]:
        project = project_from_id(project_id)
        environments = project.environments(readonly=True)
        environments.sort(key=lambda e: e.created_at or datetime.min)
        return [_env_response(e) for e in environments]

    @app.get(
        "/api/projects/{project_id}/environments/{environment_id}",
        summary="Get Environment",
        tags=["Environments"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_environment(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        environment_id: Annotated[
            str, Path(description="The unique identifier of the environment.")
        ],
    ) -> EnvironmentResponse:
        return _env_response(_env_from_id(project_id, environment_id))

    @app.patch(
        "/api/projects/{project_id}/environments/{environment_id}",
        summary="Update Environment",
        tags=["Environments"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to update an environment? Changing its environment URL changes where evals run in it send their data."
        ),
    )
    async def update_environment(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        environment_id: Annotated[
            str, Path(description="The unique identifier of the environment.")
        ],
        request: EnvironmentUpdateRequest,
    ) -> EnvironmentResponse:
        environment = _env_from_id(project_id, environment_id)
        try:
            for field, value in request.model_dump(exclude_unset=True).items():
                setattr(environment, field, value)
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        environment.save_to_file()
        return _env_response(environment)

    @app.delete(
        "/api/projects/{project_id}/environments/{environment_id}",
        summary="Delete Environment",
        tags=["Environments"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to delete an environment?"
        ),
    )
    async def delete_environment(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        environment_id: Annotated[
            str, Path(description="The unique identifier of the environment.")
        ],
    ) -> None:
        """Delete an environment, if no saved eval input still resets into it.

        409 when one does. An eval input names its environment by id, so a delete that went
        through would leave every eval run on it failing to resolve the environment.
        Traces made in the environment keep their own copy of the episode, and stay readable.
        """
        project = project_from_id(project_id)
        environment = _env_from_id(project_id, environment_id)
        referencing = sum(
            1
            for task in project.tasks(readonly=True)
            for eval_input in task.eval_inputs(readonly=True)
            if eval_input.env_reset is not None
            and eval_input.env_reset.environment_id == environment.id
        )
        if referencing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Environment is still used by {referencing} eval input(s), which reset "
                    "into it by id. Deleting it would leave evals on those inputs "
                    "unable to run. Remove or change those inputs first."
                ),
            )
        environment.delete()

    @app.get(
        "/api/projects/{project_id}/environments/{environment_id}/tools",
        summary="List Environment Tools",
        description="The tools the OpenEnv environment serves, read fresh from the running server at env_url.",
        tags=["Environments"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_environment_tools(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        environment_id: Annotated[
            str, Path(description="The unique identifier of the environment.")
        ],
    ) -> list[EnvironmentToolResponse]:
        environment = _env_from_id(project_id, environment_id)
        if not environment.env_url:
            raise HTTPException(
                status_code=400,
                detail=f"Environment '{environment.name}' has no env_url. Kiln does not "
                "start environments: run the OpenEnv server and set env_url.",
            )
        try:
            tools = await shared_session_manager().list_tools(environment, fresh=True)
        except (OpenEnvError, ValueError) as e:
            raise HTTPException(status_code=502, detail=str(e))
        return [
            EnvironmentToolResponse(
                tool_id=build_env_tool_id(environment.id, tool.name),
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools
        ]
