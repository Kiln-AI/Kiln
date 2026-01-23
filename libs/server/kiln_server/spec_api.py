import random
from typing import List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import Priority, TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalOutputScore,
    EvalTemplateId,
)
from kiln_ai.datamodel.spec import Spec, SpecStatus
from kiln_ai.datamodel.spec_properties import SpecProperties, SpecType
from kiln_ai.datamodel.task_output import (
    DataSource,
    DataSourceType,
    RequirementRating,
    TaskOutput,
    TaskOutputRating,
)
from kiln_ai.utils.name_generator import generate_memorable_name
from pydantic import BaseModel, Field

# Import copilot API types to reuse in spec creation
# These are imported at module level for type exposure in OpenAPI schema
from app.desktop.studio_server.copilot_api import (
    PromptGenerationResultApi,
    SampleApi,
)
from kiln_server.task_api import task_from_id

# Constants for copilot spec creation
KILN_COPILOT_MODEL_NAME = "kiln-copilot"
KILN_COPILOT_MODEL_PROVIDER = "kiln"
KILN_ADAPTER_NAME = "kiln-adapter"
NUM_SAMPLES_PER_TOPIC = 5  # TODO: Make this 15
NUM_TOPICS = 10  # TODO: Make this 15
MIN_EVAL_EXAMPLES = 20  # TODO: Make this 100
MIN_TRAIN_EXAMPLES = 20  # TODO: Make this 100
MIN_GOLDEN_EXAMPLES = 10  # TODO: Make this 25


class UpdateSpecRequest(BaseModel):
    name: FilenameString | None = None
    definition: str | None = None
    properties: SpecProperties | None = Field(
        default=None,
        discriminator="spec_type",
    )
    priority: Priority | None = None
    status: SpecStatus | None = None
    tags: List[str] | None = None


def spec_from_id(project_id: str, task_id: str, spec_id: str) -> Spec:
    parent_task = task_from_id(project_id, task_id)
    spec = Spec.from_id_and_parent_path(spec_id, parent_task.path)
    if spec:
        return spec

    raise HTTPException(
        status_code=404,
        detail=f"Spec not found. ID: {spec_id}",
    )


class SpecCreationRequest(BaseModel):
    name: FilenameString
    definition: str
    properties: SpecProperties = Field(
        discriminator="spec_type",
    )
    priority: Priority
    status: SpecStatus
    tags: List[str]
    eval_id: str | None


class ReviewedExample(BaseModel):
    """A reviewed example from the spec review process.

    Extends SampleApi with review-specific fields for tracking
    model and user judgments on spec compliance.
    """

    input: str = Field(alias="input")
    output: str
    model_says_meets_spec: bool
    user_says_meets_spec: bool
    feedback: str

    model_config = {"populate_by_name": True}


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
    reviewed_examples: List[ReviewedExample] = Field(default_factory=list)
    judge_info: PromptGenerationResultApi
    task_description: str = ""
    task_prompt_with_few_shot: str = ""


def _spec_eval_output_score(spec_name: str) -> EvalOutputScore:
    """Create an EvalOutputScore for a spec."""
    return EvalOutputScore(
        name=spec_name,
        type=TaskOutputRatingType.pass_fail,
        instruction=f"Evaluate if the model's behaviour meets the spec: {spec_name}.",
    )


def _spec_eval_data_type(
    spec_type: SpecType, evaluate_full_trace: bool = False
) -> EvalDataType:
    """Determine the eval data type for a spec."""
    if spec_type == SpecType.reference_answer_accuracy:
        return EvalDataType.reference_answer

    if evaluate_full_trace:
        return EvalDataType.full_trace
    else:
        return EvalDataType.final_answer


def _spec_eval_template(spec_type: SpecType) -> EvalTemplateId | None:
    """Get the eval template for a spec type."""
    match spec_type:
        case SpecType.appropriate_tool_use:
            return EvalTemplateId.tool_call
        case SpecType.reference_answer_accuracy:
            return EvalTemplateId.rag
        case SpecType.factual_correctness:
            return EvalTemplateId.factual_correctness
        case SpecType.toxicity:
            return EvalTemplateId.toxicity
        case SpecType.bias:
            return EvalTemplateId.bias
        case SpecType.maliciousness:
            return EvalTemplateId.maliciousness
        case SpecType.jailbreak:
            return EvalTemplateId.jailbreak
        case SpecType.issue:
            return EvalTemplateId.issue
        case SpecType.desired_behaviour:
            return EvalTemplateId.desired_behaviour
        case (
            SpecType.tone
            | SpecType.formatting
            | SpecType.localization
            | SpecType.hallucinations
            | SpecType.completeness
            | SpecType.nsfw
            | SpecType.taboo
            | SpecType.prompt_leakage
        ):
            return None


def _sample_and_remove(examples: list[SampleApi], n: int) -> list[SampleApi]:
    """Randomly sample and remove n items from a list.

    Mutates the input list by removing the sampled elements.
    Uses swap-and-pop for O(1) removal.
    """
    sampled: list[SampleApi] = []
    count = min(n, len(examples))

    for _ in range(count):
        if not examples:
            break
        random_index = random.randint(0, len(examples) - 1)
        # Swap with last element and pop
        examples[random_index], examples[-1] = examples[-1], examples[random_index]
        sampled.append(examples.pop())

    return sampled


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
    # Import here to avoid circular imports
    from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
        generate_batch_v1_copilot_generate_batch_post,
    )
    from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
        GenerateBatchInput,
        GenerateBatchOutput,
        HTTPValidationError,
    )
    from app.desktop.studio_server.api_client.kiln_server_client import (
        get_authenticated_client,
    )
    from app.desktop.studio_server.copilot_api import _get_api_key

    api_key = _get_api_key()
    client = get_authenticated_client(api_key)

    generate_input = GenerateBatchInput.from_dict(
        {
            "target_task_prompt": task_prompt_with_few_shot,
            "task_input_schema": task_input_schema,
            "task_output_schema": task_output_schema,
            "spec_rendered_prompt_template": spec_definition,
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


def _create_task_run_from_sample(sample: SampleApi, tag: str) -> TaskRun:
    """Create a TaskRun from a SampleApi (without parent set)."""
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "adapter_name": KILN_ADAPTER_NAME,
            "model_name": KILN_COPILOT_MODEL_NAME,
            "model_provider": KILN_COPILOT_MODEL_PROVIDER,
        },
    )

    # Access input using model_dump since SampleApi uses alias
    sample_dict = sample.model_dump(by_alias=True)
    return TaskRun(
        input=sample_dict["input"],
        input_source=data_source,
        output=TaskOutput(
            output=sample.output,
            source=data_source,
        ),
        tags=[tag],
    )


def _create_task_run_from_reviewed(
    example: ReviewedExample, tag: str, spec_name: str
) -> TaskRun:
    """Create a TaskRun from a reviewed example with rating (without parent set)."""
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "adapter_name": KILN_ADAPTER_NAME,
            "model_name": KILN_COPILOT_MODEL_NAME,
            "model_provider": KILN_COPILOT_MODEL_PROVIDER,
        },
    )

    rating_key = f"named::{spec_name}"
    rating_value = 1.0 if example.user_says_meets_spec else 0.0

    return TaskRun(
        input=example.input,
        input_source=data_source,
        output=TaskOutput(
            output=example.output,
            source=data_source,
            rating=TaskOutputRating(
                type=TaskOutputRatingType.five_star,
                value=5.0,  # Default value, actual rating is in requirement_ratings
                requirement_ratings={
                    rating_key: RequirementRating(
                        type=TaskOutputRatingType.pass_fail,
                        value=rating_value,
                    )
                },
            ),
        ),
        tags=[tag],
    )


def _create_dataset_task_runs(
    all_examples: list[SampleApi],
    reviewed_examples: list[ReviewedExample],
    eval_tag: str,
    train_tag: str,
    golden_tag: str,
    spec_name: str,
) -> list[TaskRun]:
    """Create TaskRuns for eval, train, and golden datasets.

    Samples from all_examples (mutating it) and creates TaskRuns for:
    - Eval dataset (MIN_EVAL_EXAMPLES)
    - Train dataset (MIN_TRAIN_EXAMPLES)
    - Golden dataset (reviewed examples + unrated examples to reach MIN_GOLDEN_EXAMPLES)

    Returns TaskRuns without parent set - caller must set parent.
    """
    task_runs: list[TaskRun] = []

    # Sample examples for eval and train datasets
    eval_examples = _sample_and_remove(all_examples, MIN_EVAL_EXAMPLES)
    train_examples = _sample_and_remove(all_examples, MIN_TRAIN_EXAMPLES)

    # Create TaskRuns for eval examples
    for example in eval_examples:
        task_runs.append(_create_task_run_from_sample(example, eval_tag))

    # Create TaskRuns for train examples
    for example in train_examples:
        task_runs.append(_create_task_run_from_sample(example, train_tag))

    # Create unrated golden examples from remaining pool if needed
    unrated_golden_count = max(0, MIN_GOLDEN_EXAMPLES - len(reviewed_examples))
    if unrated_golden_count > 0:
        unrated_golden_examples = _sample_and_remove(all_examples, unrated_golden_count)
        for example in unrated_golden_examples:
            task_runs.append(_create_task_run_from_sample(example, golden_tag))

    # Create TaskRuns for reviewed examples with ratings
    for reviewed in reviewed_examples:
        task_runs.append(
            _create_task_run_from_reviewed(reviewed, golden_tag, spec_name)
        )

    return task_runs


def connect_spec_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/spec")
    async def create_spec(
        project_id: str, task_id: str, spec_data: SpecCreationRequest
    ) -> Spec:
        task = task_from_id(project_id, task_id)
        spec = Spec(
            parent=task,
            name=spec_data.name,
            definition=spec_data.definition,
            properties=spec_data.properties,
            priority=spec_data.priority,
            status=spec_data.status,
            tags=spec_data.tags,
            eval_id=spec_data.eval_id,
        )
        spec.save_to_file()
        return spec

    @app.get("/api/projects/{project_id}/tasks/{task_id}/specs")
    async def get_specs(project_id: str, task_id: str) -> List[Spec]:
        parent_task = task_from_id(project_id, task_id)
        return parent_task.specs(readonly=True)

    @app.get("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def get_spec(project_id: str, task_id: str, spec_id: str) -> Spec:
        return spec_from_id(project_id, task_id, spec_id)

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def update_spec(
        project_id: str, task_id: str, spec_id: str, request: UpdateSpecRequest
    ) -> Spec:
        spec = spec_from_id(project_id, task_id, spec_id)

        # Update all provided fields
        if request.name is not None:
            spec.name = request.name
        if request.definition is not None:
            spec.definition = request.definition
        if request.properties is not None:
            spec.properties = request.properties
        if request.priority is not None:
            spec.priority = request.priority
        if request.status is not None:
            spec.status = request.status
        if request.tags is not None:
            spec.tags = request.tags

        spec.save_to_file()
        return spec

    @app.delete("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def delete_spec(project_id: str, task_id: str, spec_id: str) -> None:
        spec = spec_from_id(project_id, task_id, spec_id)

        # Delete associated eval if it exists
        if spec.eval_id:
            parent_task = task_from_id(project_id, task_id)
            eval = Eval.from_id_and_parent_path(spec.eval_id, parent_task.path)
            if eval:
                eval.delete()

        spec.delete()

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
        template = _spec_eval_template(spec_type)
        output_scores = [_spec_eval_output_score(request.name)]
        eval_set_filter_id = f"tag::{eval_tag}"
        eval_configs_filter_id = f"tag::{golden_tag}"
        evaluation_data_type = _spec_eval_data_type(
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
        task_runs = _create_dataset_task_runs(
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
        # Save everything in order: eval first (parent), then config, then runs, then spec
        eval_model.save_to_file()
        eval_config.save_to_file()
        for run in task_runs:
            run.save_to_file()
        spec.save_to_file()

        return spec
