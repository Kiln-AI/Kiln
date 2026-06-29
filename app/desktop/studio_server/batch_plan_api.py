import json
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_server.project_api import project_from_id
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
from app.desktop.studio_server.batch_plan_task import (
    BATCH_PLAN_INSTRUCTION,
    BATCH_PLAN_OUTPUT_SCHEMA,
)
from app.desktop.studio_server.data_gen_api import _resolve_task_runtime_prompt
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from app.desktop.studio_server.utils.response_utils import unwrap_response

# Where the batch plan runs:
#   True  → in-process LOCAL execution (Sonnet 4.6 / OpenRouter, your keys),
#           so it can be tested without a kiln_server.
#   False → proxy to kiln_server's /v1/copilot/batch_plan (the GCP path). Point
#           it at a local kiln_server with KILN_SERVER_BASE_URL=http://localhost:<port>,
#           or leave the default (https://api.kiln.tech) for staging/prod.
# This is the single switch for the local→GCP move.
RUN_BATCH_PLAN_LOCALLY = True


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


def _build_batch_plan_input(
    task_prompt: str,
    task_input_schema: str | None,
    task_output_schema: str | None,
    input_data_guide: str | None,
    user_guidance: str,
    count: int,
) -> str:
    """Assemble the planner's free-form composite input. Section ordering and
    XML tag names follow the batch planner's data guide presentation defaults:
    input profile → input schema → output schema → instruction → guidance → count.
    """
    parts: list[str] = []
    if input_data_guide and input_data_guide.strip():
        parts.append(f"<input_data_guide>\n{input_data_guide}\n</input_data_guide>")
    if task_input_schema:
        parts.append(f"<task_input_schema>\n{task_input_schema}\n</task_input_schema>")
    if task_output_schema:
        parts.append(
            f"<task_output_schema>\n{task_output_schema}\n</task_output_schema>"
        )
    parts.append(f"<task_instruction>\n{task_prompt}\n</task_instruction>")
    parts.append(f"<user_guidance>\n{user_guidance}\n</user_guidance>")
    parts.append(f"<count>\n{count}\n</count>")
    return "\n\n".join(parts)


# ===========================================================================
# LOCAL EXECUTION — runs the batch planner in-process (used when
# RUN_BATCH_PLAN_LOCALLY is True) so it can be tested without a kiln_server.
# The GCP/kiln_server path lives in `_run_batch_plan_kiln_server` below.
# ===========================================================================
def _build_local_batch_plan_task(project: Project) -> Task:
    return Task(
        name="BatchPlanner",
        parent=project,
        instruction=BATCH_PLAN_INSTRUCTION,
        input_json_schema=None,
        output_json_schema=BATCH_PLAN_OUTPUT_SCHEMA,
    )


async def _run_batch_plan_local(
    project: Project, composite_input: str
) -> BatchPlanApiOutput:
    task = _build_local_batch_plan_task(project)
    run_config = KilnAgentRunConfigProperties(
        model_name="claude_sonnet_4_6",
        model_provider_name=ModelProviderName.openrouter,
        prompt_id=PromptGenerators.SIMPLE,
        structured_output_mode=StructuredOutputMode.json_schema,
        thinking_level="medium",
        temperature=1.0,
        top_p=1.0,
    )
    adapter = adapter_for_task(
        task,
        run_config_properties=run_config,
        base_adapter_config=AdapterConfig(allow_saving=False),
    )
    run = await adapter.invoke(composite_input)
    if run.output is None or run.output.output is None:
        raise HTTPException(status_code=500, detail="Batch planner returned no output.")
    try:
        parsed = json.loads(run.output.output)
    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Batch planner returned malformed output: {e}",
        )
    prompts = parsed.get("prompts")
    summary = parsed.get("summary")
    if not isinstance(prompts, list) or not isinstance(summary, str):
        raise HTTPException(
            status_code=500,
            detail="Batch planner output missing 'prompts' or 'summary'.",
        )
    return BatchPlanApiOutput(prompts=prompts, summary=summary)


# ===========================================================================


# ===========================================================================
# GCP / kiln_server PROXY — runs the batch planner as a copilot call on
# kiln_server (used when RUN_BATCH_PLAN_LOCALLY is False). kiln_server assembles
# the composite from these named fields, so we send them structured rather than
# pre-joined.
# ===========================================================================
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
    result = unwrap_response(
        detailed,
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
        # Gate on copilot connection (required for both local and kiln_server).
        get_copilot_api_key()

        task = task_from_id(project_id, task_id)

        # Task context is derived server-side; the client only sends guidance,
        # count, and the optional data guide.
        task_prompt = _resolve_task_runtime_prompt(task)

        if RUN_BATCH_PLAN_LOCALLY:
            project = project_from_id(project_id)
            composite_input = _build_batch_plan_input(
                task_prompt=task_prompt,
                task_input_schema=task.input_json_schema,
                task_output_schema=task.output_json_schema,
                input_data_guide=input.data_guide,
                user_guidance=input.guidance,
                count=input.count,
            )
            return await _run_batch_plan_local(project, composite_input)

        return await _run_batch_plan_kiln_server(
            task_prompt=task_prompt,
            task_input_schema=task.input_json_schema,
            task_output_schema=task.output_json_schema,
            input_data_guide=input.data_guide,
            user_guidance=input.guidance,
            count=input.count,
        )
