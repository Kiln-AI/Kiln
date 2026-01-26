import logging

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    clarify_spec_v1_copilot_clarify_spec_post,
    generate_batch_v1_copilot_generate_batch_post,
    question_spec_v1_copilot_question_spec_post,
    refine_spec_v1_copilot_refine_spec_post,
    refine_spec_with_answers_v1_copilot_refine_spec_with_answers_post,
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
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    QuestionSet as QuestionSetServerApi,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    RefineSpecWithQuestionAnswersResponse as RefineSpecWithQuestionAnswersResponseServerApi,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SpecQuestionerInput as SpecQuestionerInputServerApi,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SubmitAnswersRequest as SubmitAnswersRequestServerApi,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.util.spec_creation import (
    NUM_SAMPLES_PER_TOPIC,
    NUM_TOPICS,
    ReviewedExample,
    SampleApi,
    create_dataset_task_runs,
    spec_eval_data_type,
    spec_eval_output_score,
    spec_eval_template,
)
from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, Priority
from kiln_ai.datamodel.eval import Eval, EvalConfig, EvalConfigType
from kiln_ai.datamodel.questions import (
    QuestionSet,
    RefineSpecWithQuestionAnswersResponse,
    SpecQuestionerInput,
    SubmitAnswersRequest,
)
from kiln_ai.datamodel.spec import Spec, SpecStatus
from kiln_ai.datamodel.spec_properties import SpecProperties
from kiln_ai.utils.config import Config
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.task_api import task_from_id
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Pydantic input models (replacing attrs-based client models)
class TaskInfoApi(BaseModel):
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
    target_task_info: TaskInfoApi
    target_specification: str
    num_samples_per_topic: int
    num_topics: int
    providers: list[ModelProviderName]
    num_exemplars: int = Field(default=10)


class RefineSpecApiInput(BaseModel):
    target_task_info: TaskInfoApi
    spec: SpecInfoApi
    examples_with_feedback: list[ExampleWithFeedbackApi]


class GenerateBatchApiInput(BaseModel):
    target_task_info: TaskInfoApi
    topic_generation_task_info: TaskInfoApi
    input_generation_task_info: TaskInfoApi
    target_specification: str
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


class GenerateBatchApiOutput(BaseModel):
    data_by_topic: dict[str, list[SampleApi]]


class CreateSpecWithCopilotRequest(BaseModel):
    """Request model for creating a spec with Kiln Copilot.

    This endpoint uses Kiln Copilot to:
    - Generate batch examples for eval, train, and golden datasets
    - Create a judge eval config
    - Create an eval with appropriate template/output scores
    - Create and save the spec

    If you don't want to use copilot, use the regular POST /spec endpoint instead.

    The client is responsible for building:
    - definition: The spec definition string (use buildSpecDefinition on client)
    - properties: The spec properties object (filtered, with spec_type included)
    """

    name: FilenameString
    definition: str = Field(
        description="The spec definition string, built by client using buildSpecDefinition()"
    )
    properties: SpecProperties = Field(
        discriminator="spec_type",
        description="The spec properties object, pre-built by client with spec_type included",
    )
    evaluate_full_trace: bool = False
    reviewed_examples: list[ReviewedExample] = Field(default_factory=list)
    judge_info: PromptGenerationResultApi
    task_description: str = ""
    task_prompt_with_few_shot: str = ""


async def _generate_copilot_examples(
    task_prompt_with_few_shot: str,
    task_input_schema: str,
    task_output_schema: str,
    spec_definition: str,
) -> list[SampleApi]:
    """Generate examples via the Kiln Copilot API.

    Calls the copilot generate_batch endpoint and returns a flat list of SampleApi objects.
    Raises HTTPException on API errors.
    """
    api_key = _get_api_key()
    client = get_authenticated_client(api_key)

    generate_input = GenerateBatchInput.from_dict(
        {
            "target_task_prompt": task_prompt_with_few_shot,
            "task_input_schema": task_input_schema,
            "task_output_schema": task_output_schema,
            "target_specification": spec_definition,
            "num_samples_per_topic": NUM_SAMPLES_PER_TOPIC,
            "num_topics": NUM_TOPICS,
        }
    )

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

    if not isinstance(result, GenerateBatchOutput):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate batch: Unexpected response type {type(result)}",
        )

    # Convert result to flat list of SampleApi
    examples: list[SampleApi] = []
    data_dict = result.to_dict().get("data_by_topic", {})
    for topic_examples in data_dict.values():
        for ex in topic_examples:
            examples.append(
                SampleApi(
                    input=ex.get("input", ""),
                    output=ex.get("output", ""),
                )
            )

    return examples


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

    @app.post("/api/copilot/question_spec")
    async def question_spec(
        input: SpecQuestionerInput,
    ) -> QuestionSet:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        questioner_input = SpecQuestionerInputServerApi.from_dict(input.model_dump())

        result = await question_spec_v1_copilot_question_spec_post.asyncio(
            client=client,
            body=questioner_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500, detail="Failed to generate questions: No response"
            )

        if isinstance(result, HTTPValidationError):
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {result.to_dict()}",
            )

        if isinstance(result, QuestionSetServerApi):
            return QuestionSet.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate questions: Unexpected response type {type(result)}",
        )

    @app.post("/api/copilot/refine_spec_with_question_answers")
    async def submit_question_answers(
        request: SubmitAnswersRequest,
    ) -> RefineSpecWithQuestionAnswersResponse:
        api_key = _get_api_key()
        client = get_authenticated_client(api_key)

        submit_input = SubmitAnswersRequestServerApi.from_dict(request.model_dump())

        result = await refine_spec_with_answers_v1_copilot_refine_spec_with_answers_post.asyncio(
            client=client,
            body=submit_input,
        )

        if result is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to refine spec with question answers: No response",
            )

        if isinstance(result, HTTPValidationError):
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {result.to_dict()}",
            )

        if isinstance(result, RefineSpecWithQuestionAnswersResponseServerApi):
            return RefineSpecWithQuestionAnswersResponse.model_validate(
                result.to_dict()
            )

        raise HTTPException(
            status_code=500,
            detail=f"Failed to refine spec with question answers: Unexpected response type {type(result)}",
        )

    @app.post("/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot")
    async def create_spec_with_copilot(
        project_id: str, task_id: str, request: CreateSpecWithCopilotRequest
    ) -> Spec:
        """Create a spec using Kiln Copilot.

        This endpoint uses Kiln Copilot to create a spec with:
        1. An eval for the spec with appropriate template
        2. Batch examples via copilot API for eval, train, and golden datasets
        3. A judge eval config (if judge_info provided)
        4. The spec itself

        If you don't need copilot, use POST /spec instead.

        All models are validated before any saves occur. If validation fails,
        no data is persisted.
        """
        task = task_from_id(project_id, task_id)

        # Generate tag suffixes
        eval_tag_suffix = request.name.lower().replace(" ", "_")
        eval_tag = f"eval_{eval_tag_suffix}"
        train_tag = f"eval_train_{eval_tag_suffix}"
        golden_tag = f"eval_golden_{eval_tag_suffix}"

        # Extract spec_type from properties (discriminated union)
        spec_type = request.properties["spec_type"]

        # Determine eval properties
        template = spec_eval_template(spec_type)
        output_scores = [spec_eval_output_score(request.name)]
        eval_set_filter_id = f"tag::{eval_tag}"
        eval_configs_filter_id = f"tag::{golden_tag}"
        evaluation_data_type = spec_eval_data_type(
            spec_type, request.evaluate_full_trace
        )

        # Build models but don't save yet, collect all models first
        models_to_save: list[Eval | EvalConfig | TaskRun | Spec] = []

        # 1. Create the Eval
        eval_model = Eval(
            parent=task,
            name=request.name,
            description=None,
            template=template,
            output_scores=output_scores,
            eval_set_filter_id=eval_set_filter_id,
            eval_configs_filter_id=eval_configs_filter_id,
            template_properties=None,
            evaluation_data_type=evaluation_data_type,
        )
        models_to_save.append(eval_model)

        # 2. Create judge eval config
        eval_config = EvalConfig(
            parent=eval_model,
            name=generate_memorable_name(),
            config_type=EvalConfigType.llm_as_judge,
            model_name=request.judge_info.task_metadata.model_name,
            model_provider=request.judge_info.task_metadata.model_provider_name,
            properties={
                "eval_steps": [request.judge_info.prompt],
                "task_description": request.task_description,
            },
        )
        models_to_save.append(eval_config)

        # Set as default config after ID is assigned
        eval_model.current_config_id = eval_config.id

        # 3. Generate examples via copilot API
        all_examples = await _generate_copilot_examples(
            task_prompt_with_few_shot=request.task_prompt_with_few_shot,
            task_input_schema=str(task.input_json_schema)
            if task.input_json_schema
            else "",
            task_output_schema=str(task.output_json_schema)
            if task.output_json_schema
            else "",
            spec_definition=request.definition,
        )

        # 4. Create TaskRuns for eval, train, and golden datasets
        task_runs = create_dataset_task_runs(
            all_examples=all_examples,
            reviewed_examples=request.reviewed_examples,
            eval_tag=eval_tag,
            train_tag=train_tag,
            golden_tag=golden_tag,
            spec_name=request.name,
        )
        for run in task_runs:
            run.parent = task
        models_to_save.extend(task_runs)

        # 5. Create the Spec using pre-computed definition and properties from client
        spec = Spec(
            parent=task,
            name=request.name,
            definition=request.definition,
            properties=request.properties,
            priority=Priority.p1,
            status=SpecStatus.active,
            tags=[],
            eval_id=eval_model.id,
        )
        models_to_save.append(spec)

        # All models are now created and validated via Pydantic.
        # Save everything, with cleanup on failure.
        saved_models: list[Eval | EvalConfig | TaskRun | Spec] = []
        try:
            eval_model.save_to_file()
            saved_models.append(eval_model)

            eval_config.save_to_file()
            saved_models.append(eval_config)

            for run in task_runs:
                run.save_to_file()
                saved_models.append(run)

            spec.save_to_file()
            saved_models.append(spec)
        except Exception:
            # Clean up any models that were successfully saved before the error
            for model in reversed(saved_models):
                try:
                    model.delete()
                except Exception:
                    # Log cleanup error but continue, the original error is more important
                    logger.exception(
                        f"Failed to delete {type(model).__name__} during cleanup"
                    )
            raise

        return spec
