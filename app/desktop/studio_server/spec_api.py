from typing import Any

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.dev_spec import (
    clarify_spec_api_dev_clarify_spec_post,
    refine_spec_api_dev_refine_spec_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ClarifySpecInput,
    ExampleWithFeedback,
    RefineSpecInput,
    RefineSpecOutput,
    SpecInfo,
    SubsampleBatchOutput,
    TaskInfo,
)
from app.desktop.studio_server.api_client.kiln_server_client import server_client
from fastapi import FastAPI, HTTPException
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
    task_info: dict[str, Any]
    spec: dict[str, Any]
    examples_with_feedback: list[dict[str, Any]]


class GenerateBatchApiInput(BaseModel):
    task_prompt_with_few_shot: str
    task_input_schema: str
    task_output_schema: str
    spec_rendered_prompt_template: str
    num_samples_per_topic: int
    num_topics: int
    enable_scoring: bool = Field(default=False)


def connect_spec_api(app: FastAPI):
    @app.post("/api/spec/clarify")
    async def clarify_spec(input: ClarifySpecApiInput) -> dict[str, Any]:
        clarify_input = ClarifySpecInput(
            task_prompt_with_few_shot=input.task_prompt_with_few_shot,
            task_input_schema=input.task_input_schema,
            task_output_schema=input.task_output_schema,
            spec_rendered_prompt_template=input.spec_rendered_prompt_template,
            num_samples_per_topic=input.num_samples_per_topic,
            num_topics=input.num_topics,
            num_exemplars=input.num_exemplars,
        )

        result = await clarify_spec_api_dev_clarify_spec_post.asyncio(
            client=server_client,
            body=clarify_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500, detail="Failed to clarify spec: No response"
            )

        if isinstance(result, SubsampleBatchOutput):
            return result.to_dict()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to clarify spec: Unexpected response type {type(result)}",
        )

    @app.post("/api/spec/refine")
    async def refine_spec(input: RefineSpecApiInput) -> dict[str, Any]:
        task_info = TaskInfo.from_dict(input.task_info)
        spec = SpecInfo.from_dict(input.spec)
        examples_with_feedback = [
            ExampleWithFeedback.from_dict(ex) for ex in input.examples_with_feedback
        ]

        refine_input = RefineSpecInput(
            task_prompt_with_few_shot=input.task_prompt_with_few_shot,
            task_input_schema=input.task_input_schema,
            task_output_schema=input.task_output_schema,
            task_info=task_info,
            spec=spec,
            examples_with_feedback=examples_with_feedback,
        )

        result = await refine_spec_api_dev_refine_spec_post.asyncio(
            client=server_client,
            body=refine_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500, detail="Failed to refine spec: No response"
            )

        if isinstance(result, RefineSpecOutput):
            return result.to_dict()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to refine spec: Unexpected response type {type(result)}",
        )

    @app.post("/api/spec/generate_batch")
    async def generate_batch(input: GenerateBatchApiInput) -> dict[str, Any]:
        clarify_input = ClarifySpecInput(
            task_prompt_with_few_shot=input.task_prompt_with_few_shot,
            task_input_schema=input.task_input_schema,
            task_output_schema=input.task_output_schema,
            spec_rendered_prompt_template=input.spec_rendered_prompt_template,
            num_samples_per_topic=input.num_samples_per_topic,
            num_topics=input.num_topics,
            num_exemplars=10,
        )

        result = await clarify_spec_api_dev_clarify_spec_post.asyncio(
            client=server_client,
            body=clarify_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500, detail="Failed to generate batch: No response"
            )

        if isinstance(result, SubsampleBatchOutput):
            return result.to_dict()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate batch: Unexpected response type {type(result)}",
        )
