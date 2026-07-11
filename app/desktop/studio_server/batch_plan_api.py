from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Path
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval
from pydantic import BaseModel, Field

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    batch_plan_v1_copilot_batch_plan_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    BatchPlanInput as BatchPlanInputClient,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    BatchPlanOutput as BatchPlanOutputClient,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.data_gen_api import _resolve_task_runtime_prompt
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from app.desktop.studio_server.utils.response_utils import unwrap_response


class BatchPlanApiInput(BaseModel):
    guidance: str = Field(
        default="",
        description="User guidance describing this batch (distribution, focus, edge cases).",
    )
    count: int = Field(
        description="Number of inputs to plan — the planner returns one prompt per input.",
        ge=1,
        le=500,
    )
    data_guide: str | None = Field(
        default=None,
        description="The task's input data guide (input profile) to include, or null to omit.",
    )


class BatchPlanApiOutput(BaseModel):
    prompts: list[str] = Field(
        description="One tailored prompt per input; length equals the requested count."
    )
    summary: str = Field(
        description="A short, user-facing overview of the planned batch."
    )


# kiln_server assembles the composite planner input from these named fields, so
# we send them structured rather than pre-joined.
async def _run_batch_plan_kiln_server(
    task_prompt: str,
    task_input_schema: str | None,
    task_output_schema: str | None,
    input_data_guide: str | None,
    user_guidance: str,
    count: int,
) -> BatchPlanApiOutput:
    api_key = get_copilot_api_key()
    client = get_authenticated_client(api_key)
    try:
        detailed = await batch_plan_v1_copilot_batch_plan_post.asyncio_detailed(
            client=client,
            body=BatchPlanInputClient(
                task_prompt=task_prompt,
                count=count,
                task_input_schema=task_input_schema,
                task_output_schema=task_output_schema,
                input_data_guide=input_data_guide,
                user_guidance=user_guidance,
            ),
        )
    except httpx.HTTPError as e:
        # Network-level failure (unreachable host, TLS, timeout). Without this
        # the raw exception surfaces to the client as a generic 500.
        raise HTTPException(
            status_code=502,
            detail="Couldn't reach the Kiln batch planning service. Check your connection and that your Kiln server supports batch planning.",
        ) from e
    # A non-2xx (e.g. a 404 from a Kiln server that doesn't have batch planning
    # deployed) is propagated with this message rather than a bare "Unknown
    # error" — a raw 404 reads like the endpoint is missing.
    result = unwrap_response(
        detailed,
        default_detail="The Kiln batch planning service returned an error. Your Kiln server may not support batch planning yet.",
        none_detail="Failed to plan the batch. Please try again.",
    )
    if isinstance(result, BatchPlanOutputClient):
        return BatchPlanApiOutput.model_validate(result.to_dict())
    raise HTTPException(status_code=500, detail="Unknown error planning batch.")


def connect_batch_plan_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/batch_plan",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval(
            "Plan a synthetic batch with Copilot?"
        ),
    )
    async def batch_plan(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: BatchPlanApiInput,
    ) -> BatchPlanApiOutput:
        """Plan a synthetic batch: turn the user's guidance + count into one
        tailored prompt per input (plus a user-facing summary). Requires a
        connected Kiln Pro / Copilot key (connection only, no paid tier)."""
        get_copilot_api_key()

        task = task_from_id(project_id, task_id)

        # Task context is derived server-side; the client only sends guidance,
        # count, and the optional data guide.
        task_prompt = _resolve_task_runtime_prompt(task)

        return await _run_batch_plan_kiln_server(
            task_prompt=task_prompt,
            task_input_schema=task.input_json_schema,
            task_output_schema=task.output_json_schema,
            input_data_guide=input.data_guide,
            user_guidance=input.guidance,
            count=input.count,
        )
