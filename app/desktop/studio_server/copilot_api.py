import csv
import io
import json
import logging
from typing import Annotated

import jsonschema

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    clarify_spec_v1_copilot_clarify_spec_post,
    generate_batch_v1_copilot_generate_batch_post,
    question_spec_v1_copilot_question_spec_post,
    refine_spec_v1_copilot_refine_spec_post,
    refine_spec_with_answers_v1_copilot_refine_spec_with_answers_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs import (
    get_data_guide_job_result_v1_jobs_data_guide_job_job_id_result_get,
    get_job_status_v1_jobs_job_type_job_id_status_get,
    start_data_guide_job_v1_jobs_data_guide_job_start_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ClarifySpecInput,
    ClarifySpecOutput,
    DraftInputDataGuideInput,
    GenerateBatchInput,
    GenerateBatchOutput,
    JobStatus,
    JobType,
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
)
from app.desktop.studio_server.api_models.copilot_models import (
    DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH,
    DataGuideJobResultApiOutput,
    DataGuideJobStatusApiOutput,
    ParseImportFileApiOutput,
    StartDataGuideJobApiInput,
    StartDataGuideJobApiOutput,
    ClarifySpecApiInput,
    ClarifySpecApiOutput,
    GenerateBatchApiInput,
    GenerateBatchApiOutput,
    RefineSpecApiInput,
    ReviewedChainApi,
    ReviewedExample,
    SpecQuestionerApiInput,
    SyntheticDataGenerationSessionConfigApi,
    TaskInfoApi,
)
from app.desktop.studio_server.utils.copilot_utils import (
    create_dataset_task_runs,
    find_multi_turn_chain_leaves,
    generate_copilot_examples,
    get_copilot_api_key,
    rate_multi_turn_chain_leaves,
    tag_multi_turn_chains_for_eval,
    unrate_multi_turn_chain_leaves,
    untag_multi_turn_chains_for_eval,
)
from app.desktop.studio_server.api_models.eval_builder_models import JudgeConfig
from app.desktop.studio_server.utils.eval_builder_utils import (
    build_judge_prompt_template,
)
from app.desktop.studio_server.utils.response_utils import unwrap_response
from fastapi import FastAPI, File, HTTPException, Path, UploadFile
from kiln_ai.datamodel import ClaimReview, Feedback, TaskRun
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.eval import Eval, EvalConfig, EvalConfigType, LlmJudgeProperties
from kiln_ai.datamodel.json_schema import validate_schema
from kiln_ai.datamodel.spec import (
    Spec,
    SpecStatus,
    SyntheticDataGenerationSessionConfig,
    SyntheticDataGenerationStepConfig,
    TaskSample,
)
from kiln_ai.datamodel.spec_properties import SpecProperties, SpecType
from kiln_ai.datamodel.task_output import TaskOutputRating
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
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
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
    reviewed_chains: list[ReviewedChainApi] = Field(
        default_factory=list,
        description="The human's review verdicts, one per reviewed chain keyed "
        "by leaf TaskRun id. Each becomes a golden RequirementRating on the "
        "chain leaf (plus Feedback / per-claim grades when present).",
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
    judge_info: JudgeConfig = Field(
        description="The judge to persist as the eval's V2 config — the same "
        "shape (and, from the builder, the same values) the review step ran, "
        "so the calibrated judge is the one that ships."
    )
    sdg_session_config: SyntheticDataGenerationSessionConfigApi | None = None
    multi_turn: MultiTurnSaveInfo | None = None
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


# --- Data Guide draft job plumbing -----------------------------------------
#
# The Data Guide draft runs as a kiln_server background job so the heavy
# summarize+aggregate work happens server-side and survives a flaky
# connection. The studio server proxies the job's start / status / result
# lifecycle so the web UI owns polling and the user can leave the page and
# come back (or get nudged back via the task-wide progress widget).
#
# These go through the generated kiln_ai_server_client like the other copilot
# and job endpoints. Note the start/result endpoints live under the
# `data_guide_job` path segment, while status goes through the shared
# `/{job_type}/{job_id}/status` route keyed by `JobType.DATA_GUIDE_JOB`.


async def _start_data_guide_job(
    client: AuthenticatedClient, body: DraftInputDataGuideInput
) -> str:
    """Start the Data Guide draft job on kiln_server and return its job id.
    Raises HTTPException on failure."""
    detailed = (
        await start_data_guide_job_v1_jobs_data_guide_job_start_post.asyncio_detailed(
            client=client,
            body=body,
        )
    )
    response = unwrap_response(
        detailed,
        default_detail="Failed to start the data guide job. Please try again.",
    )
    if not response.job_id:
        raise HTTPException(
            status_code=500,
            detail="Data guide job did not return a job id.",
        )
    return response.job_id


async def _get_data_guide_job_status(client: AuthenticatedClient, job_id: str) -> str:
    """Fetch the current status of a Data Guide draft job. Raises HTTPException
    on a transport/server error.

    The status endpoint can flip to `succeeded` slightly before the draft output
    is committed and retrievable. To keep the UI honest, we hold the reported
    status at `running` until the result is actually available — so the spinner
    and the task-wide indicator stay "in progress" and the client never tries to
    fetch (and error on) an unfinished result. A job that finished but produced
    an empty draft still reports `succeeded` here: that's a real failure the
    result fetch surfaces, not an in-flight state.
    """
    detailed = await get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed(
        job_type=JobType.DATA_GUIDE_JOB,
        job_id=job_id,
        client=client,
    )
    response = unwrap_response(
        detailed,
        default_detail="Failed to check the data guide job status.",
    )
    if response.status == JobStatus.SUCCEEDED and not await _data_guide_result_ready(
        client, job_id
    ):
        return JobStatus.RUNNING.value
    return response.status.value


async def _data_guide_result_ready(client: AuthenticatedClient, job_id: str) -> bool:
    """Whether the draft job's result endpoint reports the job as finished
    (`succeeded`) — i.e. the draft is retrievable. False while the result
    endpoint still reads as in-progress (it can lag the status endpoint). A
    transport/server error is treated as "ready" so it surfaces through the
    normal result fetch instead of pinning the UI in-progress forever."""
    try:
        detailed = await get_data_guide_job_result_v1_jobs_data_guide_job_job_id_result_get.asyncio_detailed(
            job_id=job_id,
            client=client,
        )
        response = unwrap_response(
            detailed,
            default_detail="Failed to fetch the data guide result.",
        )
        return response.status == JobStatus.SUCCEEDED
    except HTTPException:
        return True


async def _get_data_guide_job_result(client: AuthenticatedClient, job_id: str) -> str:
    """Fetch the draft guide markdown from a completed Data Guide draft job.
    Raises HTTPException on failure or an empty result."""
    detailed = await get_data_guide_job_result_v1_jobs_data_guide_job_job_id_result_get.asyncio_detailed(
        job_id=job_id,
        client=client,
    )
    response = unwrap_response(
        detailed,
        default_detail="Failed to fetch the data guide result.",
    )
    # The result endpoint can return before the draft is actually available —
    # the job's status can read `succeeded` slightly ahead of the output being
    # committed. Distinguish "not finished yet" (caller should keep polling)
    # from "finished but genuinely empty" so we don't surface a misleading
    # empty-draft error while the job is still wrapping up.
    if response.status != JobStatus.SUCCEEDED:
        raise HTTPException(
            status_code=425,  # Too Early
            detail="The data guide draft is still being generated. Please wait.",
        )
    draft_guide = getattr(response.output, "draft_guide", "") or ""
    if not isinstance(draft_guide, str) or not draft_guide.strip():
        raise HTTPException(
            status_code=500,
            detail="Copilot returned an empty draft guide.",
        )
    return draft_guide


def _finalize_import_rows(rows: list[str], too_long: int) -> ParseImportFileApiOutput:
    """Shared tail for both parsers: turn accepted rows + a skipped-for-length
    count into the response, choosing a clear error when nothing remains."""
    if not rows:
        if too_long > 0:
            return ParseImportFileApiOutput(
                rows=[],
                error=(
                    "All examples were over the "
                    f"{DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH:,} character limit."
                ),
            )
        return ParseImportFileApiOutput(rows=[], error="No examples found in the file.")
    warning = None
    if too_long > 0:
        warning = (
            f"{too_long} example{'' if too_long == 1 else 's'} over the "
            f"{DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH:,} character limit "
            "will be skipped."
        )
    return ParseImportFileApiOutput(rows=rows, warning=warning)


def _parse_csv_import(
    content: str, input_json_schema: str | None
) -> ParseImportFileApiOutput:
    """Parse a single-column CSV of input examples with the stdlib csv reader
    (RFC 4180 — handles quoted commas/newlines/escaped quotes).

    Plaintext tasks take each cell as the raw input. Structured-input tasks take
    each cell as a JSON object, validated against the task's input schema (author
    these in a spreadsheet so the JSON's commas/quotes are escaped on export).

    Enforces a single column: any record that parses to more than one field
    means an unescaped separator (or a genuine multi-column file). Rather than
    silently keep column one and drop the rest, we reject and tell the user to
    quote values that contain commas.
    """
    rows_with_numbers: list[tuple[int, list[str]]] = []
    for row_number, fields in enumerate(csv.reader(io.StringIO(content)), start=1):
        if all(field.strip() == "" for field in fields):
            continue  # blank record
        rows_with_numbers.append((row_number, fields))

    if not rows_with_numbers:
        return ParseImportFileApiOutput(rows=[], error="No examples found in the file.")

    # Drop an optional single-cell "input" header.
    _, first_fields = rows_with_numbers[0]
    if len(first_fields) == 1 and first_fields[0].strip().lower() == "input":
        rows_with_numbers = rows_with_numbers[1:]

    if any(len(fields) > 1 for _, fields in rows_with_numbers):
        return ParseImportFileApiOutput(
            rows=[],
            error="Invalid CSV format. Expected only one column.",
        )

    accepted: list[str] = []
    too_long = 0
    for row_number, fields in rows_with_numbers:
        value = fields[0].strip()
        if value == "":
            continue
        if input_json_schema is not None:
            # Structured task: each cell must be a JSON object matching the schema.
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return ParseImportFileApiOutput(
                    rows=[], error=f"Row {row_number} is not valid JSON."
                )
            try:
                validate_schema(parsed, input_json_schema, require_object=False)
            except jsonschema.exceptions.ValidationError as e:
                return ParseImportFileApiOutput(
                    rows=[],
                    error=(
                        f"Row {row_number} does not match the task input schema: "
                        f"{e.message}"
                    ),
                )
            value = json.dumps(parsed)
        if len(value) > DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH:
            too_long += 1
            continue
        accepted.append(value)
    return _finalize_import_rows(accepted, too_long)


def _validate_structured_examples(input_json_schema: str, examples: list[str]) -> None:
    """Validate each candidate input example against the task's input JSON
    schema, raising HTTPException(422) listing every example that fails.

    For structured-input tasks each example must be a JSON value matching the
    schema. The web UI does only a shallow check at import time; this is the
    authoritative gate (full schema validation, mirroring the dataset import
    path) run before the expensive draft job kicks off.
    """
    errors: list[str] = []
    for idx, raw in enumerate(examples):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            errors.append(f"Example {idx + 1} is not valid JSON.")
            continue
        try:
            validate_schema(parsed, input_json_schema, require_object=False)
        except jsonschema.exceptions.ValidationError as e:
            errors.append(
                f"Example {idx + 1} does not match the task input schema: {e.message}"
            )
    if errors:
        raise HTTPException(status_code=422, detail=" ".join(errors))


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
        "/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/start",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval(
            "Draft a data guide from input examples with Copilot?"
        ),
    )
    async def start_data_guide_job(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        input: StartDataGuideJobApiInput,
    ) -> StartDataGuideJobApiOutput:
        """Kick off the input data guide draft job on kiln_server and return its
        job id. The job summarizes and aggregates the heterogeneous list of
        input examples (manual entries, existing task runs, uploaded text
        documents) into a draft guide.

        The job runs in the background so the user can leave the page and come
        back. The web UI polls `.../data_guide_job/{job_id}/status` and, once
        the job succeeds, fetches `.../data_guide_job/{job_id}/result` and
        generates preview inputs locally via the existing
        `/data_gen_guide_preview` flow.
        """
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        task = task_from_id(project_id, task_id)

        # Structured-input tasks: validate every example against the real input
        # schema before kicking off the draft job. The client only does a
        # shallow check at import, so this is the authoritative gate.
        if task.input_json_schema is not None:
            _validate_structured_examples(task.input_json_schema, input.input_examples)

        resolved_task_prompt = _resolve_task_runtime_prompt(task)

        # Everything except the examples is derived server-side from the task:
        # the prompt is resolved (not trusted from the client) and the input
        # schema is read straight off the task. The output schema and
        # task.description are never forwarded — output policy must not reach the
        # guide LLM.
        body = DraftInputDataGuideInput(
            task_prompt=resolved_task_prompt,
            task_input_schema=task.input_json_schema,
            input_examples=input.input_examples,
        )

        job_id = await _start_data_guide_job(client, body)
        return StartDataGuideJobApiOutput(job_id=job_id)

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/parse_import_file",
        tags=["Copilot"],
        openapi_extra=ALLOW_AGENT,
    )
    async def parse_import_file(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        file: Annotated[
            UploadFile,
            File(description="The file of input examples to parse and validate."),
        ],
    ) -> ParseImportFileApiOutput:
        """Parse an uploaded bulk-import file of input examples for the data
        guide, server-side.

        Both task types use a single-column CSV (parsed with the stdlib csv
        reader). Plaintext tasks take each cell as the raw input; structured
        tasks take each cell as a JSON object, validated against the task's input
        schema. Returns the parsed example strings plus any whole-file `error` or
        partial-skip `warning` so the web UI just renders the result.
        """
        task = task_from_id(project_id, task_id)
        raw = await file.read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=422,
                detail="The file must be UTF-8 encoded text.",
            )

        return _parse_csv_import(content, task.input_json_schema)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/status",
        tags=["Copilot"],
        openapi_extra=ALLOW_AGENT,
    )
    async def data_guide_job_status(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        job_id: Annotated[
            str, Path(description="The data guide draft job identifier.")
        ],
    ) -> DataGuideJobStatusApiOutput:
        """Return the current status of a data guide draft job (e.g. running,
        succeeded, failed, cancelled). The web UI polls this while showing the
        analyzing animation and the task-wide progress widget."""
        # Validate the route scope — 404 on an unknown project/task path rather
        # than serving by job_id alone under any task.
        task_from_id(project_id, task_id)
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        status = await _get_data_guide_job_status(client, job_id)
        return DataGuideJobStatusApiOutput(status=status)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/result",
        tags=["Copilot"],
        openapi_extra=ALLOW_AGENT,
    )
    async def data_guide_job_result(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        job_id: Annotated[
            str, Path(description="The data guide draft job identifier.")
        ],
    ) -> DataGuideJobResultApiOutput:
        """Return the draft guide markdown produced by a completed data guide
        draft job. The web UI calls this once the job status is `succeeded`."""
        # Validate the route scope — 404 on an unknown project/task path rather
        # than serving by job_id alone under any task.
        task_from_id(project_id, task_id)
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        draft_guide = await _get_data_guide_job_result(client, job_id)
        return DataGuideJobResultApiOutput(draft_guide=draft_guide)

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

        # Idempotency guard against re-submits after a completed save (the
        # save is slow, so users retry). Case-insensitive because the eval
        # tags and rating keys are derived from the lowercased name — two
        # specs differing only by case would share a tag namespace. Two
        # requests in flight at once can still race past this check —
        # acceptable for a single-user studio.
        if any(
            spec.name.lower() == request.name.lower()
            for spec in task.specs(readonly=True)
        ):
            raise HTTPException(
                status_code=409,
                detail=f"A spec named '{request.name}' already exists for this task.",
            )

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
            # Reviewed chains must reference leaves of THIS batch, each at
            # most once — check up front so a stale or malformed review fails
            # before any models are created (rate_multi_turn_chain_leaves
            # re-checks membership as a backstop).
            leaf_ids = {leaf.id for leaf in multi_turn_leaves if leaf.id}
            reviewed_ids = [rc.leaf_run_id for rc in request.multi_turn.reviewed_chains]
            missing = [rid for rid in reviewed_ids if rid not in leaf_ids]
            if missing:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Reviewed chain leaves not found in batch "
                        f"'{request.multi_turn.batch_tag}': {', '.join(missing)}."
                    ),
                )
            duplicates = sorted(
                {rid for rid in reviewed_ids if reviewed_ids.count(rid) > 1}
            )
            if duplicates:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Each chain leaf can be reviewed at most once; "
                        f"duplicated: {', '.join(duplicates)}."
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

        # 2. Create the judge eval config — V2 shape, the same judge the review
        # step ran transiently (one judge, persisted vs transient). V2 rails
        # give it an editable prompt_template the refine loop can write back
        # into, instead of the legacy llm_as_judge dispatch.
        eval_config = EvalConfig(
            parent=eval,
            name=generate_memorable_name(),
            config_type=EvalConfigType.v2,
            properties=LlmJudgeProperties(
                model_name=request.judge_info.model_name,
                model_provider=request.judge_info.model_provider,
                prompt_template=build_judge_prompt_template(
                    request.judge_info.prompt,
                    multi_turn=request.evaluate_full_trace,
                ),
            ),
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
        rated_leaves: list[
            tuple[TaskRun, TaskOutputRating | None, list[Feedback | ClaimReview]]
        ] = []
        try:
            eval.save_to_file()
            saved_models.append(eval)

            eval_config.save_to_file()
            saved_models.append(eval_config)

            for run in task_runs:
                run.save_to_file()
                saved_models.append(run)
                if dataset_runs is not None:
                    dataset_runs.save_pending_children(run)

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
                # Then write the human's verdicts: golden ratings (+ feedback
                # and per-claim grades) on the reviewed chain leaves.
                rate_multi_turn_chain_leaves(
                    multi_turn_leaves,
                    request.multi_turn.reviewed_chains,
                    spec_name=request.name,
                    rated_out=rated_leaves,
                )
        except Exception:
            # Reverse any leaf mutations we made in this run (ratings first —
            # they were applied last) before deleting the saved models, so a
            # failed multi-turn save doesn't leave orphan ratings or tags
            # pointing at a now-deleted eval.
            if rated_leaves:
                unrate_multi_turn_chain_leaves(rated_leaves)
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
