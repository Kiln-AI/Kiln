import asyncio
import logging
import time
from typing import Annotated, Any

import httpx
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
from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    AuthenticatedClient,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.data_gen_api import (
    _resolve_task_runtime_prompt,
    generate_input_preview_samples,
)
from app.desktop.studio_server.api_models.copilot_models import (
    DraftInputDataGuideApiInput,
    DraftInputDataGuideApiOutput,
    DraftInputDataGuidePreviewSampleApi,
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
    generate_copilot_examples,
    get_copilot_api_key,
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
from kiln_ai.datamodel.spec_properties import SpecProperties
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
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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
    judge_info: SyntheticDataGenerationStepConfigApi
    sdg_session_config: SyntheticDataGenerationSessionConfigApi
    task_description: str = ""
    task_prompt_with_example: str = ""
    task_sample: TaskSample | None = None


# --- Data Guide job (Cloud Run Job) plumbing -------------------------------
#
# The Data Guide draft runs as a kiln_server job so the heavy
# summarize+aggregate work happens server-side and survives a flaky
# connection. The studio server polls the job to completion under the hood;
# the endpoint's response contract is unchanged, so the UI keeps showing its
# loading animation.
#
# Raw httpx is used because the generated kiln_ai_server_client doesn't expose
# the data_guide_job endpoints yet; swap to the typed client methods once it's
# regenerated post-deploy. Note the path asymmetry: start/result use the
# underscore segment `data_guide_job`, while status uses the hyphenated
# job-type value `data-guide-job` (the shared /{job_type}/{job_id}/status route).
_DATA_GUIDE_JOB_TYPE = "data-guide-job"
_DATA_GUIDE_JOB_POLL_INTERVAL_SECONDS = 3.0
# The job's own Cloud Run timeout is 30 min (staging); allow a little beyond
# that before we stop polling, so we never give up while the job is still alive.
_DATA_GUIDE_JOB_MAX_WAIT_SECONDS = 32 * 60
_DATA_GUIDE_JOB_FINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


def _kiln_server_error_detail(response: httpx.Response, fallback: str) -> str:
    """Surface kiln_server's human-readable `message` from an error body."""
    if response.content.startswith(b"{"):
        try:
            return response.json().get("message") or fallback
        except ValueError:
            pass
    return fallback


async def _run_data_guide_job(
    client: AuthenticatedClient, draft_payload: dict[str, Any]
) -> str:
    """Start the Data Guide job on kiln_server, poll it to completion, and
    return the draft guide markdown. Raises HTTPException on failure."""
    async with client.get_async_httpx_client() as http:
        start_response = await http.post(
            "/v1/jobs/data_guide_job/start", json=draft_payload
        )
        if start_response.status_code != 200:
            raise HTTPException(
                status_code=start_response.status_code,
                detail=_kiln_server_error_detail(
                    start_response,
                    "Failed to start the data guide job. Please try again.",
                ),
            )
        job_id = start_response.json().get("job_id")
        if not job_id:
            raise HTTPException(
                status_code=500,
                detail="Data guide job did not return a job id.",
            )

        deadline = time.monotonic() + _DATA_GUIDE_JOB_MAX_WAIT_SECONDS
        status = ""
        while True:
            status_response = await http.get(
                f"/v1/jobs/{_DATA_GUIDE_JOB_TYPE}/{job_id}/status"
            )
            if status_response.status_code != 200:
                raise HTTPException(
                    status_code=status_response.status_code,
                    detail=_kiln_server_error_detail(
                        status_response,
                        "Failed to check the data guide job status.",
                    ),
                )
            status = str(status_response.json().get("status", "")).lower()
            if status in _DATA_GUIDE_JOB_FINAL_STATUSES:
                break
            if time.monotonic() >= deadline:
                raise HTTPException(
                    status_code=504,
                    detail="The data guide job timed out. Please try again.",
                )
            await asyncio.sleep(_DATA_GUIDE_JOB_POLL_INTERVAL_SECONDS)

        if status != "succeeded":
            raise HTTPException(
                status_code=502,
                detail=f"The data guide job did not succeed (status: {status}).",
            )

        result_response = await http.get(f"/v1/jobs/data_guide_job/{job_id}/result")
        if result_response.status_code != 200:
            raise HTTPException(
                status_code=result_response.status_code,
                detail=_kiln_server_error_detail(
                    result_response,
                    "Failed to fetch the data guide result.",
                ),
            )
        output = result_response.json().get("output") or {}
        draft_guide = output.get("draft_guide", "")

    if not isinstance(draft_guide, str) or not draft_guide.strip():
        raise HTTPException(
            status_code=500,
            detail="Copilot returned an empty draft guide.",
        )
    return draft_guide


def connect_copilot_api(app: FastAPI):
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
        "/api/projects/{project_id}/tasks/{task_id}/copilot/draft_input_data_guide",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval(
            "Draft a data guide from input examples with Copilot?"
        ),
    )
    async def draft_input_data_guide(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: DraftInputDataGuideApiInput,
    ) -> DraftInputDataGuideApiOutput:
        """Draft an input data guide from a heterogeneous list of input examples
        (manual entries, existing task runs, uploaded text documents) using the
        Kiln Copilot, plus a small set of preview inputs the user can review.

        Two-step internally: (1) run the kiln_server data guide job
        (`/v1/jobs/data_guide_job/*`), polling it to completion under the hood,
        to get the draft guide markdown, then (2) reuse the local input-preview
        helper with that draft to generate `num_preview_samples` preview inputs.
        Both go back to the client in one response so the UI can drop straight
        into the existing review/refine flow.
        """
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        task = task_from_id(project_id, task_id)
        resolved_task_prompt = _resolve_task_runtime_prompt(task)

        draft_payload = {
            "task_prompt": resolved_task_prompt,
            "task_input_schema": input.target_task_info.task_input_schema or None,
            "input_examples": input.input_examples,
        }

        # Run the draft as a kiln_server job and poll it to completion under the
        # hood (see _run_data_guide_job). The response contract is unchanged, so
        # the UI keeps showing its loading animation.
        draft_guide = await _run_data_guide_job(client, draft_payload)

        preview = await generate_input_preview_samples(
            task=task,
            guide=draft_guide,
            run_config_properties=input.run_config_properties,
            num_samples=input.num_preview_samples,
        )

        return DraftInputDataGuideApiOutput(
            draft_guide=draft_guide,
            preview_samples=[
                DraftInputDataGuidePreviewSampleApi(input=s.input) for s in preview
            ],
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

        # Build models but don't save yet, collect all models first
        models_to_save: list[Eval | EvalConfig | TaskRun | Spec] = []

        # 1. Create the Eval
        eval = Eval(
            parent=task,
            name=request.name,
            description=None,
            template=template,
            output_scores=output_scores,
            eval_set_filter_id=eval_set_filter_id,
            train_set_filter_id=train_set_filter_id,
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

        # 3. Generate examples via copilot API
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

        # 4. Create TaskRuns for eval, train, and golden datasets
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

        # 5. Create the Spec using pre-computed definition and properties from client
        topic_generation_config = request.sdg_session_config.topic_generation_config
        input_generation_config = request.sdg_session_config.input_generation_config
        output_generation_config = request.sdg_session_config.output_generation_config

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
            synthetic_data_generation_session_config=SyntheticDataGenerationSessionConfig(
                topic_generation_config=SyntheticDataGenerationStepConfig(
                    model_name=topic_generation_config.task_metadata.model_name,
                    provider_name=topic_generation_config.task_metadata.model_provider_name,
                    prompt=topic_generation_config.prompt,
                ),
                input_generation_config=SyntheticDataGenerationStepConfig(
                    model_name=input_generation_config.task_metadata.model_name,
                    provider_name=input_generation_config.task_metadata.model_provider_name,
                    prompt=input_generation_config.prompt,
                ),
                output_generation_config=SyntheticDataGenerationStepConfig(
                    model_name=output_generation_config.task_metadata.model_name,
                    provider_name=output_generation_config.task_metadata.model_provider_name,
                    prompt=output_generation_config.prompt,
                ),
            ),
        )
        models_to_save.append(spec)

        # All models are now created and validated via Pydantic.
        # Save everything, with cleanup on failure.
        saved_models: list[Eval | EvalConfig | TaskRun | Spec] = []
        try:
            eval.save_to_file()
            saved_models.append(eval)

            eval_config.save_to_file()
            saved_models.append(eval_config)

            for run in task_runs:
                run.save_to_file()
                saved_models.append(run)
                dataset_runs.save_pending_feedback(run)

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
