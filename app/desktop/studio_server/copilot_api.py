from typing import Any

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    clarify_spec_v1_copilot_clarify_spec_post,
    generate_batch_v1_copilot_generate_batch_post,
    refine_spec_v1_copilot_refine_spec_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ClarifySpecInput,
    ClarifySpecOutput,
    ExampleWithFeedback,
    GenerateBatchInput,
    GenerateBatchOutput,
    HTTPValidationError,
    RefineSpecInput,
    RefineSpecOutput,
    SpecInfo,
    TaskInfo,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from fastapi import FastAPI, HTTPException
from kiln_ai.utils.config import Config
from pydantic import BaseModel, Field


class ClarifySpecApiInput(BaseModel):
    task_prompt_with_few_shot: str
    task_input_schema: str
    task_output_schema: str
    spec_rendered_prompt_template: str
    num_samples_per_topic: int
    num_topics: int
    num_exemplars: int = Field(default=10)


class RefineSpecApiInput(BaseModel):
    task_prompt_with_few_shot: str
    task_input_schema: str
    task_output_schema: str
    task_info: TaskInfo
    spec: SpecInfo
    examples_with_feedback: list[ExampleWithFeedback]


class GenerateBatchApiInput(BaseModel):
    task_prompt_with_few_shot: str
    task_input_schema: str
    task_output_schema: str
    spec_rendered_prompt_template: str
    num_samples_per_topic: int
    num_topics: int
    enable_scoring: bool = Field(default=False)


def _get_api_key() -> str:
    """Get the Kiln Copilot API key from config, raising an error if not set."""
    api_key = Config.shared().kiln_copilot_api_key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Kiln Copilot API key not configured. Please connect your API key in settings.",
        )
    return api_key


def connect_copilot_api(app: FastAPI):
    @app.post("/api/copilot/clarify_spec")
    async def clarify_spec(input: ClarifySpecApiInput) -> dict[str, Any]:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        clarify_input = ClarifySpecInput(**input.model_dump())

        result = await clarify_spec_v1_copilot_clarify_spec_post.asyncio(
            client=client,
            body=clarify_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500, detail="Failed to clarify spec: No response"
            )

        if isinstance(result, HTTPValidationError):
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {result.to_dict()}",
            )

        if isinstance(result, ClarifySpecOutput):
            return result.to_dict()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to clarify spec: Unexpected response type {type(result)}",
        )

    @app.post("/api/copilot/refine_spec")
    async def refine_spec(input: RefineSpecApiInput) -> dict[str, Any]:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        refine_input = RefineSpecInput(**input.model_dump())

        result = await refine_spec_v1_copilot_refine_spec_post.asyncio(
            client=client,
            body=refine_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500, detail="Failed to refine spec: No response"
            )

        if isinstance(result, HTTPValidationError):
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {result.to_dict()}",
            )

        if isinstance(result, RefineSpecOutput):
            return result.to_dict()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to refine spec: Unexpected response type {type(result)}",
        )

    @app.post("/api/copilot/generate_batch")
    async def generate_batch(input: GenerateBatchApiInput) -> dict[str, Any]:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        generate_input = GenerateBatchInput(**input.model_dump())

        result = await generate_batch_v1_copilot_generate_batch_post.asyncio(
            client=client,
            body=generate_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500, detail="Failed to generate batch: No response"
            )

        if isinstance(result, HTTPValidationError):
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {result.to_dict()}",
            )

        if isinstance(result, GenerateBatchOutput):
            return result.to_dict()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate batch: Unexpected response type {type(result)}",
        )
