from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    clarify_spec_v1_copilot_clarify_spec_post,
    generate_batch_v1_copilot_generate_batch_post,
    refine_spec_v1_copilot_refine_spec_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ClarifySpecInput,
    ClarifySpecOutput,
    GenerateBatchInput,
    GenerateBatchOutput,
    HTTPValidationError,
    RefineSpecInput,
    RefineSpecOutput,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.utils.config import Config
from pydantic import BaseModel, Field


# Pydantic input models (replacing attrs-based client models)
class TargetTaskInfoApi(BaseModel):
    target_task_prompt: str
    target_task_input_schema: str
    target_task_output_schema: str


class SpecInfoApi(BaseModel):
    spec_fields: dict[str, str]
    spec_field_current_values: dict[str, str]


class ExampleWithFeedbackApi(BaseModel):
    model_config = {"populate_by_name": True}

    user_agrees_with_judge: bool
    input: str = Field(alias="input")
    output: str
    fails_specification: bool
    user_feedback: str | None = None


class ClarifySpecApiInput(BaseModel):
    target_task_prompt: str
    task_input_schema: str
    task_output_schema: str
    spec_rendered_prompt_template: str
    num_samples_per_topic: int
    num_topics: int
    providers: list[ModelProviderName]
    num_exemplars: int = Field(default=10)


class RefineSpecApiInput(BaseModel):
    target_task_info: TargetTaskInfoApi
    spec: SpecInfoApi
    examples_with_feedback: list[ExampleWithFeedbackApi]


class GenerateBatchApiInput(BaseModel):
    target_task_prompt: str
    task_input_schema: str
    task_output_schema: str
    spec_rendered_prompt_template: str
    num_samples_per_topic: int
    num_topics: int


class SubsampleBatchOutputItemApi(BaseModel):
    input: str = Field(alias="input")
    output: str
    fails_specification: bool


class TaskMetadataApi(BaseModel):
    model_name: str
    model_provider_name: ModelProviderName


class PromptGenerationResultApi(BaseModel):
    task_metadata: TaskMetadataApi
    prompt: str


class ClarifySpecApiOutput(BaseModel):
    examples_for_feedback: list[SubsampleBatchOutputItemApi]
    judge_result: PromptGenerationResultApi
    topic_generation_result: PromptGenerationResultApi
    input_generation_result: PromptGenerationResultApi


class NewProposedSpecEditApi(BaseModel):
    spec_field_name: str
    proposed_edit: str
    reason_for_edit: str


class RefineSpecApiOutput(BaseModel):
    new_proposed_spec_edits: list[NewProposedSpecEditApi]
    not_incorporated_feedback: str | None


class SampleApi(BaseModel):
    input: str = Field(alias="input")
    output: str


class GenerateBatchApiOutput(BaseModel):
    data_by_topic: dict[str, list[SampleApi]]


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
    async def clarify_spec(input: ClarifySpecApiInput) -> ClarifySpecApiOutput:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        clarify_input = ClarifySpecInput.from_dict(input.model_dump())

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
            return ClarifySpecApiOutput.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail=f"Failed to clarify spec: Unexpected response type {type(result)}",
        )

    @app.post("/api/copilot/refine_spec")
    async def refine_spec(input: RefineSpecApiInput) -> RefineSpecApiOutput:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        refine_input = RefineSpecInput.from_dict(input.model_dump())

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
            return RefineSpecApiOutput.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail=f"Failed to refine spec: Unexpected response type {type(result)}",
        )

    @app.post("/api/copilot/generate_batch")
    async def generate_batch(input: GenerateBatchApiInput) -> GenerateBatchApiOutput:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        generate_input = GenerateBatchInput.from_dict(input.model_dump())

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
            return GenerateBatchApiOutput.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate batch: Unexpected response type {type(result)}",
        )
