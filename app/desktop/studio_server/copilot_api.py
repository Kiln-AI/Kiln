import logging
from typing import Annotated

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
    RefineSpecInput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    QuestionSet as QuestionSetServerApi,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    RefineSpecApiOutput as RefineSpecApiOutputClient,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SpecQuestionerApiInput as SpecQuestionerApiInputServerApi,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SubmitAnswersRequest as SubmitAnswersRequestServerApi,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.api_models.copilot_models import (
    ClarifySpecApiInput,
    ClarifySpecApiOutput,
    GenerateBatchApiInput,
    GenerateBatchApiOutput,
    RefineSpecApiInput,
    ReviewedExample,
    SpecQuestionerApiInput,
    SyntheticDataGenerationSessionConfigApi,
    SyntheticDataGenerationStepConfigApi,
    TaskInfoApi,
)
from app.desktop.studio_server.utils.copilot_utils import (
    create_dataset_task_runs,
    find_multi_turn_chain_leaves,
    generate_copilot_examples,
    get_copilot_api_key,
    tag_multi_turn_chains_for_eval,
    untag_multi_turn_chains_for_eval,
)
from app.desktop.studio_server.utils.response_utils import unwrap_response
from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.eval import Eval, EvalConfig, EvalConfigType
from kiln_ai.datamodel.spec import (
    Spec,
    SpecStatus,
    SyntheticDataGenerationSessionConfig,
    SyntheticDataGenerationStepConfig,
    TaskSample,
)
from kiln_ai.datamodel.spec_properties import SpecProperties, SpecType
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.task_api import task_from_id
from kiln_server.utils.spec_utils import (
    generate_spec_eval_filter_ids,
    generate_spec_eval_tags,
    spec_eval_data_type,
    spec_eval_output_score,
    spec_eval_template,
)
from libs.core.kiln_ai.datamodel.copilot_models.questions import (
    QuestionSet,
    RefineSpecApiOutput,
    SubmitAnswersRequest,
)
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

logger = logging.getLogger(__name__)


class ClassifySpecDescriptionInput(BaseModel):
    """Free-text description of an eval the user wants to build. The
    endpoint maps it to a `SpecType` and pre-fills the property_values for
    that type so the v2 builder can skip the template-carousel step
    entirely.
    """

    description: str = Field(
        description="Free-text description of what the eval should check."
    )
    task_prompt: str | None = Field(
        default=None,
        description="Optional task prompt for context (improves classification "
        "accuracy when the spec relates to a specific task).",
    )


class ClassifySpecDescriptionOutput(BaseModel):
    """Classified spec type + suggested name + spec_type-specific property
    values. Keys in `property_values` correspond to `FieldConfig.key`
    entries in `spec_field_configs[spec_type]` (see
    app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/select_template/spec_templates.ts).
    """

    spec_type: SpecType = Field(description="The classified spec type.")
    suggested_name: str = Field(
        description="A filename-safe name for the new spec, derived from the description."
    )
    property_values: dict[str, str] = Field(
        description="Pre-filled property values for the chosen spec_type. "
        "Keys correspond to the field_configs of that spec_type."
    )


class MultiTurnSaveInfo(BaseModel):
    """Identifies an existing multi-turn synthetic-user batch to turn into an Eval.
    The endpoint walks chains tagged with this batch_tag and applies eval/golden
    filter tags instead of generating new examples.
    """

    batch_tag: str = Field(
        description="The batch_tag emitted by the multi-turn synthetic-user runner "
        "(see kiln_ai.synthetic_user.runner). Identifies the set of conversation "
        "chains already persisted to disk that this Eval should evaluate."
    )


class CreateSpecWithCopilotRequest(BaseModel):
    """Request model for creating a spec with Kiln Copilot.

    Two synthesis paths are supported, exactly one must be set per request:

    - **Single-turn:** caller supplies `sdg_session_config`. Endpoint calls
      `generate_copilot_examples` for fresh I/O pairs, splits them into
      eval/train/golden datasets, and tags new TaskRuns.

    - **Multi-turn:** caller supplies `multi_turn` with a `batch_tag` pointing
      at chains already on disk (created earlier by the synthetic-user runner).
      Endpoint tags the existing chain leaves with eval/golden filter tags;
      no new TaskRuns are created. `evaluate_full_trace` must be True.

    If you don't want copilot at all, use POST /spec instead.

    The client is responsible for building:
    - definition: the spec definition string (buildSpecDefinition on client)
    - properties: the spec properties object (filtered, with spec_type included)
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
    judge_info: SyntheticDataGenerationStepConfigApi
    sdg_session_config: SyntheticDataGenerationSessionConfigApi | None = None
    multi_turn: MultiTurnSaveInfo | None = None
    task_description: str = ""
    task_prompt_with_example: str = ""
    task_sample: TaskSample | None = None

    @model_validator(mode="after")
    def validate_synthesis_path(self) -> Self:
        if self.multi_turn is not None and self.sdg_session_config is not None:
            raise ValueError(
                "Pass exactly one of `multi_turn` or `sdg_session_config` — not both."
            )
        if self.multi_turn is None and self.sdg_session_config is None:
            raise ValueError(
                "Must pass one of `multi_turn` (for multi-turn chains already on "
                "disk) or `sdg_session_config` (for fresh single-turn synthesis)."
            )
        if self.multi_turn is not None and not self.evaluate_full_trace:
            raise ValueError(
                "Multi-turn save requires `evaluate_full_trace=True` — the eval "
                "evaluates full conversation traces, not single I/O pairs."
            )
        return self


def connect_copilot_api(app: FastAPI):
    @app.post(
        "/api/copilot/classify_spec_description",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval(
            "Classify a free-text spec description?"
        ),
    )
    async def classify_spec_description(
        input: ClassifySpecDescriptionInput,
    ) -> ClassifySpecDescriptionOutput:
        """Stub for spec classification — kiln_server classifier hasn't
        shipped. Returns 501 so callers can fall back to manual selection.
        """
        raise HTTPException(
            status_code=501,
            detail="Spec classification isn't implemented yet.",
        )

    @app.post(
        "/api/copilot/clarify_spec",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval("Run Copilot spec clarification?"),
    )
    async def clarify_spec(input: ClarifySpecApiInput) -> ClarifySpecApiOutput:
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        clarify_input = ClarifySpecInput.from_dict(input.model_dump())

        detailed_result = (
            await clarify_spec_v1_copilot_clarify_spec_post.asyncio_detailed(
                client=client,
                body=clarify_input,
            )
        )
        result = unwrap_response(
            detailed_result,
            none_detail="Failed to analyze spec. Please try again.",
        )

        if isinstance(result, ClarifySpecOutput):
            return ClarifySpecApiOutput.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail="Unknown error.",
        )

    @app.post(
        "/api/copilot/refine_spec",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval("Run Copilot spec refinement?"),
    )
    async def refine_spec(input: RefineSpecApiInput) -> RefineSpecApiOutput:
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        refine_input = RefineSpecInput.from_dict(input.model_dump())

        detailed_result = (
            await refine_spec_v1_copilot_refine_spec_post.asyncio_detailed(
                client=client,
                body=refine_input,
            )
        )
        result = unwrap_response(
            detailed_result,
            none_detail="Failed to refine spec with feedback. Please try again.",
        )

        if isinstance(result, RefineSpecApiOutputClient):
            return RefineSpecApiOutput.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail="Unknown error.",
        )

    @app.post(
        "/api/copilot/generate_batch",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval("Run Copilot batch generation?"),
    )
    async def generate_batch(input: GenerateBatchApiInput) -> GenerateBatchApiOutput:
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        generate_input = GenerateBatchInput.from_dict(input.model_dump())

        detailed_result = (
            await generate_batch_v1_copilot_generate_batch_post.asyncio_detailed(
                client=client,
                body=generate_input,
            )
        )
        result = unwrap_response(
            detailed_result,
            none_detail="Failed to generate synthetic data for spec. Please try again.",
        )

        if isinstance(result, GenerateBatchOutput):
            return GenerateBatchApiOutput.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail="Unknown error.",
        )

    @app.post(
        "/api/copilot/question_spec",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval("Run Copilot spec questioner?"),
    )
    async def question_spec(
        input: SpecQuestionerApiInput,
    ) -> QuestionSet:
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        questioner_input = SpecQuestionerApiInputServerApi.from_dict(input.model_dump())

        detailed_result = (
            await question_spec_v1_copilot_question_spec_post.asyncio_detailed(
                client=client,
                body=questioner_input,
            )
        )
        result = unwrap_response(
            detailed_result,
            none_detail="Failed to generate clarifying questions for spec. Please try again.",
        )

        if isinstance(result, QuestionSetServerApi):
            return QuestionSet.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail="Unknown error.",
        )

    @app.post(
        "/api/copilot/refine_spec_with_question_answers",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval(
            "Run Copilot spec refinement with question answers?"
        ),
    )
    async def submit_question_answers(
        request: SubmitAnswersRequest,
    ) -> RefineSpecApiOutput:
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        submit_input = SubmitAnswersRequestServerApi.from_dict(request.model_dump())

        detailed_result = await refine_spec_with_answers_v1_copilot_refine_spec_with_answers_post.asyncio_detailed(
            client=client,
            body=submit_input,
        )
        result = unwrap_response(
            detailed_result,
            none_detail="Failed to refine spec with question answers. Please try again.",
        )

        if isinstance(result, RefineSpecApiOutputClient):
            return RefineSpecApiOutput.model_validate(result.to_dict())

        raise HTTPException(
            status_code=500,
            detail="Unknown error.",
        )

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval("Create spec with Copilot?"),
    )
    async def create_spec_with_copilot(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        request: CreateSpecWithCopilotRequest,
    ) -> Spec:
        """Create a spec using Kiln Copilot.

        This endpoint uses Kiln Copilot to create:
        1. An Eval for the spec with the appropriate template
        2. A judge EvalConfig (LLM-as-judge)
        3. Single-turn only: batch examples via copilot API for the eval +
           golden datasets, persisted as TaskRuns
        4. The Spec itself
        Plus, for multi-turn: tag existing chain leaves with the eval/golden
        filter tags so the saved Eval picks them up as its dataset.

        If you don't need copilot, use POST /spec instead.

        All models are validated before any saves occur. If validation fails,
        no data is persisted.
        """
        task = task_from_id(project_id, task_id)

        # Generate tags and filter IDs
        eval_tag, train_tag, golden_tag = generate_spec_eval_tags(request.name)
        eval_set_filter_id, train_set_filter_id, eval_configs_filter_id = (
            generate_spec_eval_filter_ids(eval_tag, train_tag, golden_tag)
        )

        # Extract spec_type from properties (discriminated union)
        spec_type = request.properties["spec_type"]

        # Determine eval properties
        template = spec_eval_template(spec_type)
        output_scores = [spec_eval_output_score(request.name)]
        evaluation_data_type = spec_eval_data_type(
            spec_type, request.evaluate_full_trace
        )

        # Multi-turn path: find existing chain leaves up front so we 404 before
        # creating any models if the batch_tag matches nothing.
        multi_turn_leaves: list[TaskRun] = []
        if request.multi_turn is not None:
            multi_turn_leaves = find_multi_turn_chain_leaves(
                task, request.multi_turn.batch_tag
            )
            if not multi_turn_leaves:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"No multi-turn chains found for batch_tag "
                        f"'{request.multi_turn.batch_tag}'."
                    ),
                )

        # Build models but don't save yet, collect all models first
        models_to_save: list[Eval | EvalConfig | TaskRun | Spec] = []

        # 1. Create the Eval. Multi-turn has no train set in MVP
        # (see specs/projects/eval_builder_v2/design.md).
        eval = Eval(
            parent=task,
            name=request.name,
            description=None,
            template=template,
            output_scores=output_scores,
            eval_set_filter_id=eval_set_filter_id,
            train_set_filter_id=(
                None if request.multi_turn is not None else train_set_filter_id
            ),
            eval_configs_filter_id=eval_configs_filter_id,
            template_properties=None,
            evaluation_data_type=evaluation_data_type,
        )
        models_to_save.append(eval)

        # 2. Create judge eval config
        eval_config = EvalConfig(
            parent=eval,
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
        eval.current_config_id = eval_config.id

        # 3. Single-turn: synthesise examples + create TaskRuns.
        #    Multi-turn: skipped — chains already exist on disk.
        task_runs: list[TaskRun] = []
        dataset_runs = None
        sdg_session_config_for_spec: SyntheticDataGenerationSessionConfig | None = None
        if request.multi_turn is None:
            assert request.sdg_session_config is not None  # validator guarantees
            api_key = get_copilot_api_key()
            task_input_schema = (
                str(task.input_json_schema) if task.input_json_schema else ""
            )
            task_output_schema = (
                str(task.output_json_schema) if task.output_json_schema else ""
            )
            all_examples = await generate_copilot_examples(
                api_key=api_key,
                target_task_info=TaskInfoApi(
                    task_prompt=request.task_prompt_with_example,
                    task_input_schema=task_input_schema,
                    task_output_schema=task_output_schema,
                ),
                sdg_session_config=request.sdg_session_config,
                spec_definition=request.definition,
            )

            dataset_runs = create_dataset_task_runs(
                all_examples=all_examples,
                reviewed_examples=request.reviewed_examples,
                eval_tag=eval_tag,
                train_tag=train_tag,
                golden_tag=golden_tag,
                spec_name=request.name,
            )
            task_runs = dataset_runs.task_runs
            for run in task_runs:
                run.parent = task
            models_to_save.extend(task_runs)

            # Snapshot the generation config on the Spec (single-turn only).
            topic_cfg = request.sdg_session_config.topic_generation_config
            input_cfg = request.sdg_session_config.input_generation_config
            output_cfg = request.sdg_session_config.output_generation_config
            sdg_session_config_for_spec = SyntheticDataGenerationSessionConfig(
                topic_generation_config=SyntheticDataGenerationStepConfig(
                    model_name=topic_cfg.task_metadata.model_name,
                    provider_name=topic_cfg.task_metadata.model_provider_name,
                    prompt=topic_cfg.prompt,
                ),
                input_generation_config=SyntheticDataGenerationStepConfig(
                    model_name=input_cfg.task_metadata.model_name,
                    provider_name=input_cfg.task_metadata.model_provider_name,
                    prompt=input_cfg.prompt,
                ),
                output_generation_config=SyntheticDataGenerationStepConfig(
                    model_name=output_cfg.task_metadata.model_name,
                    provider_name=output_cfg.task_metadata.model_provider_name,
                    prompt=output_cfg.prompt,
                ),
            )

        # 4. Create the Spec. Multi-turn leaves sdg_session_config unset —
        # the operational state lives on the Eval (full_trace + filter_ids).
        spec = Spec(
            parent=task,
            name=request.name,
            definition=request.definition,
            properties=request.properties,
            priority=Priority.p1,
            status=SpecStatus.active,
            tags=[],
            eval_id=eval.id,
            task_sample=request.task_sample,
            synthetic_data_generation_session_config=sdg_session_config_for_spec,
        )
        models_to_save.append(spec)

        # All models are now created and validated via Pydantic.
        # Save everything, with cleanup on failure.
        saved_models: list[Eval | EvalConfig | TaskRun | Spec] = []
        tagged_leaves: list[tuple[TaskRun, set[str]]] = []
        try:
            eval.save_to_file()
            saved_models.append(eval)

            eval_config.save_to_file()
            saved_models.append(eval_config)

            for run in task_runs:
                run.save_to_file()
                saved_models.append(run)
                if dataset_runs is not None:
                    dataset_runs.save_pending_feedback(run)

            spec.save_to_file()
            saved_models.append(spec)

            # Multi-turn: tag existing chain leaves with eval/golden filter
            # tags AFTER spec has saved, so a failure here triggers the
            # rollback path below. tagged_leaves captures only the tags
            # this call added (not pre-existing ones), so untagging on
            # rollback preserves any tags the leaf had before.
            if request.multi_turn is not None:
                tag_multi_turn_chains_for_eval(
                    multi_turn_leaves,
                    eval_tag,
                    golden_tag,
                    tagged_out=tagged_leaves,
                )
        except Exception:
            # Reverse any leaf tags we added in this run before deleting the
            # saved models, so a failed multi-turn save doesn't leave orphan
            # tags pointing at a now-deleted eval.
            if tagged_leaves:
                untag_multi_turn_chains_for_eval(tagged_leaves)
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
