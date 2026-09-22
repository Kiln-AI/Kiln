import asyncio
import csv
import io
import json
import logging
import random
from http import HTTPStatus
from typing import Annotated

import httpx
import jsonschema
from fastapi import FastAPI, File, HTTPException, Path, UploadFile
from kiln_ai.datamodel import ClaimReview, Feedback, TaskRun
from kiln_ai.datamodel.basemodel import FilenameStringShort
from kiln_ai.datamodel.datamodel_enums import EvalStatus, Priority
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalInput,
    LlmJudgeProperties,
    MultiTurnDriveConfig,
)
from kiln_ai.datamodel.json_schema import validate_schema
from kiln_ai.datamodel.spec import (
    Spec,
    SpecStatus,
    SyntheticDataGenerationSessionConfig,
    SyntheticDataGenerationStepConfig,
    TaskSample,
)
from kiln_ai.datamodel.spec_properties import SpecProperties
from kiln_ai.datamodel.task_output import TaskOutputRating
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from kiln_server.utils.spec_utils import (
    ALL_SPLIT_NAMES,
    SplitShare,
    build_spec_eval,
    generate_spec_eval_tags,
    spec_eval_data_type,
    split_names,
)
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    clarify_spec_v1_copilot_clarify_spec_post,
    generate_batch_v1_copilot_generate_batch_post,
    question_spec_v1_copilot_question_spec_post,
    refine_spec_v1_copilot_refine_spec_post,
    refine_spec_with_answers_and_name_v1_copilot_refine_spec_with_answers_and_name_post,
    refine_spec_with_answers_v1_copilot_refine_spec_with_answers_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs import (
    get_data_guide_job_result_v1_jobs_data_guide_job_job_id_result_get,
    get_job_status_v1_jobs_job_type_job_id_status_get,
    start_data_guide_job_v1_jobs_data_guide_job_start_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    AuthenticatedClient,
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
    RefineSpecFromAnswersAndNameOutput as RefineSpecFromAnswersAndNameOutputClient,
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
    DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH,
    ClarifySpecApiInput,
    ClarifySpecApiOutput,
    DataGuideJobResultApiOutput,
    DataGuideJobStatusApiOutput,
    DrivenSyntheticCaseApi,
    GenerateBatchApiInput,
    GenerateBatchApiOutput,
    ParseImportFileApiOutput,
    RefineSpecApiInput,
    ReviewedChainApi,
    ReviewedExample,
    SpecQuestionerApiInput,
    StartDataGuideJobApiInput,
    StartDataGuideJobApiOutput,
    SyntheticDataGenerationSessionConfigApi,
    TaskInfoApi,
)
from app.desktop.studio_server.api_models.eval_builder_models import (
    JudgeConfig,
    spec_name_must_have_a_json_key,
)
from app.desktop.studio_server.data_gen_api import (
    _resolve_task_runtime_prompt,
)
from app.desktop.studio_server.utils.copilot_utils import (
    SingleTurnDataset,
    build_multi_turn_eval_inputs,
    build_single_turn_batch_eval_inputs,
    cases_to_mint,
    create_single_turn_dataset,
    deal_eval_inputs,
    find_multi_turn_chain_leaves,
    find_single_turn_batch_runs,
    generate_copilot_examples,
    get_copilot_api_key,
    persist_eval_slice,
    rate_reviewed_batch_runs,
    tag_golden_batch_runs,
    task_capabilities_for_task,
    task_info_payload,
    unrate_reviewed_batch_runs,
    untag_batch_runs_for_eval,
)
from app.desktop.studio_server.utils.eval_builder_utils import (
    build_judge_prompt_template,
)
from app.desktop.studio_server.utils.response_utils import (
    unwrap_response,
    upstream_route_missing,
    upstream_unreachable,
)
from libs.core.kiln_ai.datamodel.copilot_models.questions import (
    QuestionSet,
    RefineSpecApiOutput,
    SubmitAnswersRequest,
)

logger = logging.getLogger(__name__)


async def copilot_passthrough_payload(
    input: ClarifySpecApiInput | RefineSpecApiInput | SpecQuestionerApiInput,
) -> dict:
    """The kiln_server payload for a copilot route that forwards a client body.

    When the client names a project and task, the tools and skills of one of
    the task's run configs are read from local storage and attached to
    target_task_info so the copilot prompts can see what the target task can
    actually do. The client picks the config with run_config_id, or gets the
    task's default. A client that already sent capabilities keeps them. The
    ids are always stripped: they identify local storage and mean nothing to
    kiln_server.
    """
    task_info = input.target_task_info
    # Presence, not truthiness: the model already rejects a half-supplied pair,
    # so an empty id is a real (bad) id and belongs in the lookup below.
    if input.project_id is not None and input.task_id is not None:
        # A bad id 404s here, which is the honest answer: the caller asked for
        # this task's capabilities and we cannot produce them.
        task = task_from_id(input.project_id, input.task_id)
        task_tools, task_skills = await task_capabilities_for_task(
            task, input.run_config_id
        )
        task_info = task_info.model_copy(
            update={
                "task_tools": (
                    task_info.task_tools
                    if task_info.task_tools is not None
                    else task_tools
                ),
                "task_skills": (
                    task_info.task_skills
                    if task_info.task_skills is not None
                    else task_skills
                ),
            }
        )
    payload = input.model_dump(exclude={"project_id", "task_id", "run_config_id"})
    payload["target_task_info"] = task_info_payload(task_info)
    return payload


class MultiTurnSaveInfo(BaseModel):
    """An existing multi-turn synthetic-user batch to turn into an eval.

    The reviewed chains become the golden answer key; every other case is minted
    as an EvalInput the eval runner re-drives per run config.
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
    cases: list[DrivenSyntheticCaseApi] = Field(
        min_length=1,
        description="The driven synthetic-user cases of this batch. Each "
        "unreviewed one is minted as an EvalInput the runner re-drives per "
        "run config at eval time; a reviewed one is golden instead.",
    )
    drive_config: MultiTurnDriveConfig = Field(
        description="The alignment-time drive settings (synthetic-user model "
        "+ turn count), stamped on each minted EvalInput so eval-time "
        "re-drives match the conversations the judge was calibrated on.",
    )


class SingleTurnCaseApi(BaseModel):
    """One case the single-turn pipeline ran: its input and the run it ran in."""

    input: str = Field(
        description="The generated task input the batch ran, as the pipeline "
        "ran it. On a task with an input schema this is the input encoded as "
        "a JSON string."
    )
    leaf_run_id: str = Field(
        description="The id of the TaskRun this input was run in. A case "
        "whose run the human reviewed is represented by that rated run and "
        "is not minted. Empty when the pipeline recorded no run, which can "
        "never have been reviewed.",
    )


class SingleTurnSaveInfo(BaseModel):
    """An existing single-turn pipeline batch to turn into an eval.

    The reviewed runs become the golden answer key; every other case is minted as
    an EvalInput. Nothing is generated at save time.
    """

    batch_tag: str = Field(
        description="The batch_tag emitted by the single-turn pipeline "
        "(eval_builder single_turn_pipeline). Identifies the set of "
        "batch-tagged TaskRuns already persisted to disk that this Eval's "
        "golden runs are taken from."
    )
    reviewed_runs: list[ReviewedChainApi] = Field(
        default_factory=list,
        description="The human's review verdicts, one per reviewed run keyed "
        "by TaskRun id (the run itself is the leaf on this arm). Each "
        "becomes a golden RequirementRating on the run (plus Feedback / "
        "per-claim grades when present).",
    )
    inputs: list[SingleTurnCaseApi] = Field(
        min_length=1,
        description="The cases the batch actually ran. Each unreviewed one "
        "becomes an EvalInput the runner executes fresh per run config at "
        "eval time; a reviewed one is golden instead.",
    )

    @field_validator("inputs")
    @classmethod
    def inputs_must_be_non_blank(
        cls, value: list[SingleTurnCaseApi]
    ) -> list[SingleTurnCaseApi]:
        # A blank input can never be run at eval time; reject the save up
        # front instead of persisting an eval item that fails every job.
        for case in value:
            if not case.input.strip():
                raise ValueError("inputs must not contain empty entries.")
        return value


class CreateSpecWithCopilotRequest(BaseModel):
    """Request to create a spec with Kiln Copilot, along with its eval and judge.

    Exactly one synthesis path is set: `single_turn` or `multi_turn` name a batch
    of runs already on disk, while `sdg_session_config` generates fresh examples.
    The client builds `definition` and `properties`.
    """

    # Short limit: the name becomes the eval's EvalOutputScore.name (max 32)
    # — a longer name would fail deep inside Eval construction, not here.
    name: FilenameStringShort
    # The judge's score key derives from this name, and an empty key would
    # persist an eval that can never run.
    _name_has_json_key = field_validator("name")(spec_name_must_have_a_json_key)
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
    splits: list[SplitShare] | None = Field(
        default=None,
        min_length=1,
        description="The splits the eval is created with, each with its relative "
        "share of the unreviewed cases; list order wins a leftover case. Must "
        "name test. Required on a single_turn or multi_turn save.",
    )
    sdg_session_config: SyntheticDataGenerationSessionConfigApi | None = None
    multi_turn: MultiTurnSaveInfo | None = None
    single_turn: SingleTurnSaveInfo | None = None
    # Generation context for the `sdg_session_config` path only.
    task_prompt_with_example: str | None = None
    task_sample: TaskSample | None = None
    run_config_id: str | None = Field(
        default=None,
        description="Legacy `sdg_session_config` path only: the run config "
        "whose tools and skills describe the target task while examples are "
        "generated. Omit to use the task's default run config. The eval "
        "builder generates nothing, so this does not apply to it.",
    )

    @field_validator("splits")
    @classmethod
    def splits_must_name_test_once(
        cls, value: list[SplitShare] | None
    ) -> list[SplitShare] | None:
        if value is None:
            return value
        split_names(value)
        return value

    @model_validator(mode="after")
    def validate_synthesis_path(self) -> Self:
        paths_set = [
            path
            for path in (self.multi_turn, self.single_turn, self.sdg_session_config)
            if path is not None
        ]
        if len(paths_set) != 1:
            raise ValueError(
                "Pass exactly one of `single_turn` (for single-turn runs "
                "already on disk), `multi_turn` (for multi-turn chains "
                "already on disk), or `sdg_session_config` (legacy: fresh "
                "single-turn synthesis)."
            )
        # The eval builder judges the transcript, so an eval saved from a batch
        # must too, or the judge that ships is not the one the reviewer graded.
        if (
            self.multi_turn is not None or self.single_turn is not None
        ) and not self.evaluate_full_trace:
            raise ValueError(
                "An eval builder save requires `evaluate_full_trace=True` — "
                "the builder judged full traces, so the saved eval must too."
            )
        if (
            self.multi_turn is not None or self.single_turn is not None
        ) and self.splits is None:
            raise ValueError("An eval builder save requires `splits`.")
        if self.sdg_session_config is not None and self.splits is not None:
            raise ValueError(
                "`sdg_session_config` deals its own splits; omit `splits`."
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
    try:
        detailed = await start_data_guide_job_v1_jobs_data_guide_job_start_post.asyncio_detailed(
            client=client,
            body=body,
        )
    except httpx.HTTPError as e:
        raise upstream_unreachable("data guide") from e

    # This request names no resource, so an upstream 404 can only mean the route
    # isn't deployed — not "your job wasn't found".
    if detailed.status_code == HTTPStatus.NOT_FOUND:
        raise upstream_route_missing("data guide drafting")

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
    try:
        detailed = (
            await get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed(
                job_type=JobType.DATA_GUIDE_JOB,
                job_id=job_id,
                client=client,
            )
        )
    except httpx.HTTPError as e:
        raise upstream_unreachable("data guide") from e
    # This request names a job, so an upstream 404 genuinely means that job is
    # gone — propagate it as-is rather than reporting an upstream failure.
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
    except (HTTPException, httpx.HTTPError):
        return True


async def _get_data_guide_job_result(client: AuthenticatedClient, job_id: str) -> str:
    """Fetch the draft guide markdown from a completed Data Guide draft job.
    Raises HTTPException on failure or an empty result."""
    try:
        detailed = await get_data_guide_job_result_v1_jobs_data_guide_job_job_id_result_get.asyncio_detailed(
            job_id=job_id,
            client=client,
        )
    except httpx.HTTPError as e:
        raise upstream_unreachable("data guide") from e
    # Job-addressed, so an upstream 404 really means the job is gone: propagate.
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
        # 409, not 425: 425 (Too Early) is specific to TLS early data — replayable
        # bytes sent before the handshake completes — and any proxy or SDK that
        # honours it may retry on different transport terms. This is a plain
        # resource-state conflict: the job isn't finished, so a result fetch isn't
        # a request it can serve yet.
        raise HTTPException(
            status_code=409,
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
    """Check every example is a JSON value matching the task's input schema.

    Raises HTTPException(422) naming every example that fails, so one request
    reports them all.
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


def validate_reviewed_refs(
    reviewed_refs: list[ReviewedChainApi],
    batch_leaves: list[TaskRun],
    batch_tag: str,
) -> set[str]:
    """The review must describe the batch being saved, on either arm: every
    reviewed ref must name a run of THIS batch, each at most once — checked
    up front so a stale or malformed review fails before any models are
    created (rate_reviewed_batch_runs re-checks membership as a backstop).
    Returns the reviewed run ids — the golden-eligible set that drives the
    split."""
    leaf_ids = {leaf.id for leaf in batch_leaves if leaf.id}
    reviewed_ids = [ref.leaf_run_id for ref in reviewed_refs]
    missing = [rid for rid in reviewed_ids if rid not in leaf_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Reviewed runs not found in batch '{batch_tag}': {', '.join(missing)}."
            ),
        )
    duplicates = sorted({rid for rid in reviewed_ids if reviewed_ids.count(rid) > 1})
    if duplicates:
        raise HTTPException(
            status_code=422,
            detail=(
                "Each run can be reviewed at most once; "
                f"duplicated: {', '.join(duplicates)}."
            ),
        )
    return set(reviewed_ids)


def persist_spec_save(
    *,
    eval: Eval,
    eval_config: EvalConfig,
    single_turn_dataset: SingleTurnDataset | None,
    spec: Spec,
    batch_leaves: list[TaskRun],
    batch_eval_inputs: list[EvalInput],
    reviewed_refs: list[ReviewedChainApi],
    reviewed_leaf_ids: set[str],
    golden_tag: str,
    spec_name: str,
) -> None:
    """Persist every model of a spec save as one unit of work, rolling back on failure.

    An eval-builder save passes `batch_leaves` and `batch_eval_inputs`; the
    `sdg_session_config` path passes `single_turn_dataset` instead. Synchronous
    and file-I/O heavy, so callers run it off the event loop.
    """
    saved_models: list[Eval | EvalConfig | TaskRun | EvalInput | Spec] = []
    tagged_leaves: list[tuple[TaskRun, set[str]]] = []
    rated_leaves: list[
        tuple[TaskRun, TaskOutputRating | None, list[Feedback | ClaimReview]]
    ] = []
    try:
        eval.save_to_file()
        saved_models.append(eval)

        eval_config.save_to_file()
        saved_models.append(eval_config)

        # The generated golden and train runs, with their review children, then
        # the eval inputs split out of the same pool.
        if single_turn_dataset is not None:
            for run in single_turn_dataset.task_runs:
                run.save_to_file()
                saved_models.append(run)
                single_turn_dataset.save_pending_children(run)
            persist_eval_slice(single_turn_dataset.eval_inputs, saved_models)

        spec.save_to_file()
        saved_models.append(spec)

        # The eval builder's runs are tagged after the spec saves, so a failure
        # here still rolls the spec back.
        if batch_leaves:
            persist_eval_slice(batch_eval_inputs, saved_models)
            tag_golden_batch_runs(
                batch_leaves,
                reviewed_leaf_ids,
                golden_tag,
                tagged_out=tagged_leaves,
            )
            # Then write the human's verdicts: golden ratings (+ feedback and
            # per-claim grades) on the reviewed (golden) runs.
            rate_reviewed_batch_runs(
                batch_leaves,
                reviewed_refs,
                spec_name=spec_name,
                rated_out=rated_leaves,
            )
    except Exception:
        # Run mutations are reversed before the saved models are deleted, so no
        # rating or tag is left pointing at a deleted eval.
        if rated_leaves:
            unrate_reviewed_batch_runs(rated_leaves)
        if tagged_leaves:
            untag_batch_runs_for_eval(tagged_leaves)
        for model in reversed(saved_models):
            try:
                model.delete()
            except Exception:
                # Log cleanup error but continue; the original error matters more.
                logger.exception(
                    f"Failed to delete {type(model).__name__} during cleanup"
                )
        raise


def connect_copilot_api(app: FastAPI):
    @app.post(
        "/api/copilot/clarify_spec",
        tags=["Copilot"],
        openapi_extra=agent_policy_require_approval("Run Copilot spec clarification?"),
    )
    async def clarify_spec(input: ClarifySpecApiInput) -> ClarifySpecApiOutput:
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)

        clarify_input = ClarifySpecInput.from_dict(
            await copilot_passthrough_payload(input)
        )

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

        refine_input = RefineSpecInput.from_dict(
            await copilot_passthrough_payload(input)
        )

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

        questioner_input = SpecQuestionerApiInputServerApi.from_dict(
            await copilot_passthrough_payload(input)
        )

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

        # Prefer the newer route that also returns a model-suggested eval name.
        detailed_result = await refine_spec_with_answers_and_name_v1_copilot_refine_spec_with_answers_and_name_post.asyncio_detailed(
            client=client,
            body=submit_input,
        )

        # Transitional fallback: the deployed prod copilot won't serve the
        # *_and_name route until the server ships it. This request names no
        # resource, so a 404 can only mean the route isn't deployed (not a
        # missing resource) — fall back to the older route, which never carries
        # a suggested_name. Any other status (auth, 422, 500) still propagates
        # via unwrap_response below, so we don't widen the error gate.
        # Remove this fallback once the *_and_name route is universally deployed.
        if detailed_result.status_code == HTTPStatus.NOT_FOUND:
            logger.warning(
                "kiln_server refine_spec_with_answers_and_name route missing "
                "(404); falling back to refine_spec_with_answers without a "
                "suggested name."
            )
            fallback_result = await refine_spec_with_answers_v1_copilot_refine_spec_with_answers_post.asyncio_detailed(
                client=client,
                body=submit_input,
            )
            result = unwrap_response(
                fallback_result,
                none_detail="Failed to refine spec with question answers. Please try again.",
            )
            if isinstance(result, RefineSpecApiOutputClient):
                return RefineSpecApiOutput.model_validate(result.to_dict())

            raise HTTPException(
                status_code=500,
                detail="Unknown error.",
            )

        result = unwrap_response(
            detailed_result,
            none_detail="Failed to refine spec with question answers. Please try again.",
        )

        if isinstance(result, RefineSpecFromAnswersAndNameOutputClient):
            # The *_and_name output has no not_incorporated_feedback field; the
            # studio response requires it, so set it to None and carry the name.
            output = result.to_dict()
            return RefineSpecApiOutput.model_validate(
                {
                    "new_proposed_spec_edits": output["new_proposed_spec_edits"],
                    "not_incorporated_feedback": None,
                    "suggested_name": output["suggested_name"],
                }
            )

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
        3. The Spec itself
        Plus, per synthesis path:
        - Eval builder (`single_turn` / `multi_turn`): the reviewed runs are
          tagged golden and carry the human's ratings and claim reviews; every
          other case becomes an EvalInput, dealt into the splits the request
          names. Nothing is generated at save time.
        - Legacy v1 flow (`sdg_session_config`): generate examples via the
          copilot API and save them as TaskRuns, with the request's reviewed
          examples as golden.

        A test split is EvalInput items, answered fresh at eval time.

        If you don't need copilot, use POST /specs instead.

        All models are validated before any saves occur. If validation fails,
        no data is persisted.
        """
        task = task_from_id(project_id, task_id)

        # Compared by derived tags rather than by name: tags lowercase and
        # normalize spacing, so "My Spec" and "my_spec" would share a tag
        # namespace, and each other's datasets. Two requests in flight at once
        # can still race past this check.
        requested_tags = generate_spec_eval_tags(request.name)
        if any(
            generate_spec_eval_tags(spec.name) == requested_tags
            for spec in task.specs(readonly=True)
        ):
            raise HTTPException(
                status_code=409,
                detail=f"A spec named '{request.name}' (or one differing only "
                "by case or spacing) already exists for this task.",
            )

        # The tags the eval's items carry. The `sdg_session_config` path mints
        # no val items, leaving that split empty rather than absent.
        tags = generate_spec_eval_tags(request.name)
        eval_tag, train_tag, golden_tag = (
            tags.test_tag,
            tags.train_tag,
            tags.golden_tag,
        )
        # Extract spec_type from properties (discriminated union)
        spec_type = request.properties["spec_type"]
        evaluation_data_type = spec_eval_data_type(
            spec_type, request.evaluate_full_trace
        )

        # The judge template built below never renders a reference answer, so a
        # reference_answer eval would save and then mis-score every run. Only
        # direct API clients can reach this.
        if evaluation_data_type == EvalDataType.reference_answer:
            raise HTTPException(
                status_code=400,
                detail="Reference-answer specs are not supported by the spec "
                "builder yet: the saved judge would never see the reference "
                "answer. Create this eval from the Evals tab instead.",
            )

        # The batch's runs are found up front, so a batch_tag that matches
        # nothing 404s before any model is created. The reviewed ids become
        # golden and are held back from the mint below.
        batch_leaves: list[TaskRun] = []
        reviewed_refs: list[ReviewedChainApi] = []
        reviewed_leaf_ids: set[str] = set()
        if request.multi_turn is not None:
            batch_leaves = find_multi_turn_chain_leaves(
                task, request.multi_turn.batch_tag
            )
            if not batch_leaves:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"No multi-turn chains found for batch_tag "
                        f"'{request.multi_turn.batch_tag}'."
                    ),
                )
            reviewed_refs = request.multi_turn.reviewed_chains
            reviewed_leaf_ids = validate_reviewed_refs(
                reviewed_refs, batch_leaves, request.multi_turn.batch_tag
            )
        if request.single_turn is not None:
            batch_leaves = find_single_turn_batch_runs(
                task, request.single_turn.batch_tag
            )
            if not batch_leaves:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"No single-turn runs found for batch_tag "
                        f"'{request.single_turn.batch_tag}'."
                    ),
                )
            reviewed_refs = request.single_turn.reviewed_runs
            reviewed_leaf_ids = validate_reviewed_refs(
                reviewed_refs, batch_leaves, request.single_turn.batch_tag
            )

        # Every model is built and validated before anything is saved.

        # Seeded by the batch being saved, so the same batch always deals the
        # same way.
        batch_tag = (
            request.multi_turn.batch_tag
            if request.multi_turn is not None
            else request.single_turn.batch_tag
            if request.single_turn is not None
            else None
        )
        rng = random.Random(batch_tag)

        # The eval builder's cases, minus the reviewed ones: those are in the
        # eval already, as their rated golden runs. Validated here so a bad
        # persona or an input that misses the task's schema 422s before
        # anything is written.
        batch_eval_inputs: list[EvalInput] = []
        builder_save = request.multi_turn is not None or request.single_turn is not None
        if request.multi_turn is not None:
            batch_eval_inputs = build_multi_turn_eval_inputs(
                cases_to_mint(request.multi_turn.cases, reviewed_leaf_ids),
                request.multi_turn.batch_tag,
                task,
                eval_tag,
                request.multi_turn.drive_config,
            )
        if request.single_turn is not None:
            if task.input_json_schema is not None:
                # The whole payload, so the reported example numbers are the
                # caller's own positions.
                _validate_structured_examples(
                    str(task.input_json_schema),
                    [case.input for case in request.single_turn.inputs],
                )
            batch_eval_inputs = build_single_turn_batch_eval_inputs(
                [
                    case.input
                    for case in cases_to_mint(
                        request.single_turn.inputs, reviewed_leaf_ids
                    )
                ],
                request.single_turn.batch_tag,
                task,
                eval_tag,
            )

        # Deal the cases so each lands in exactly one split, holding test out
        # from what the optimizer and the judge are tuned on. The legacy v1
        # flow mints no cases and goes away with KIL-824.
        shares = request.splits
        if shares is not None:
            if not batch_eval_inputs:
                raise HTTPException(
                    status_code=422,
                    detail="Every case in this batch was reviewed, so the "
                    "eval would have no cases to run. Leave at least one "
                    "case unreviewed.",
                )
            hands = deal_eval_inputs(batch_eval_inputs, shares, tags, rng)
            if not hands["test"]:
                raise HTTPException(
                    status_code=422,
                    detail="The deal left the test split with no case, so the "
                    "eval would run nothing. Put test first in `splits`, or "
                    "save more cases.",
                )

        # 1. Create the Eval. An eval-builder save's splits hold the EvalInputs
        # dealt above; the legacy path keeps train and val as dataset runs.
        # Golden is TaskRuns on both: the runs a human graded.
        names = split_names(shares) if shares is not None else ALL_SPLIT_NAMES
        eval, _tags = build_spec_eval(
            task=task,
            name=request.name,
            spec_type=spec_type,
            evaluate_full_trace=request.evaluate_full_trace,
            priority=Priority.p1,
            status=EvalStatus.active,
            test_source="eval_input",
            train_source="eval_input" if builder_save else "task_run",
            val_source="eval_input" if builder_save else "task_run",
            split_names=names,
        )

        # 2. Create the judge eval config: the judge the review step ran, in the
        # v2 shape, whose prompt_template the refine loop can write back into.
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

        # Set as default config after ID is assigned
        eval.current_config_id = eval_config.id

        # 3. The `sdg_session_config` path only: generate examples, then build
        #    the golden and train TaskRuns and the EvalInputs from them. An
        #    eval-builder save's runs already exist on disk.
        single_turn_dataset: SingleTurnDataset | None = None
        sdg_session_config_for_spec: SyntheticDataGenerationSessionConfig | None = None
        if request.sdg_session_config is not None:
            api_key = get_copilot_api_key()
            task_input_schema = (
                str(task.input_json_schema) if task.input_json_schema else ""
            )
            task_output_schema = (
                str(task.output_json_schema) if task.output_json_schema else ""
            )
            task_tools, task_skills = await task_capabilities_for_task(
                task, request.run_config_id
            )
            all_examples = await generate_copilot_examples(
                api_key=api_key,
                target_task_info=TaskInfoApi(
                    task_prompt=request.task_prompt_with_example or "",
                    task_input_schema=task_input_schema,
                    task_output_schema=task_output_schema,
                    task_tools=task_tools,
                    task_skills=task_skills,
                ),
                sdg_session_config=request.sdg_session_config,
                spec_definition=request.definition,
            )

            single_turn_dataset = create_single_turn_dataset(
                all_examples=all_examples,
                reviewed_examples=request.reviewed_examples,
                eval_tag=eval_tag,
                train_tag=train_tag,
                golden_tag=golden_tag,
                spec_name=request.name,
                rng=rng,
            )
            for run in single_turn_dataset.task_runs:
                run.parent = task
            for eval_input in single_turn_dataset.eval_inputs:
                eval_input.parent = task

            # Snapshot the generation config on the Spec (legacy flow only).
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

        # 4. Create the Spec. Priority and status are mirrored from the eval,
        # which stays the source of truth for reads and edits.
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

        # Every model is built and validated, so persist them as one unit of
        # work. Off the event loop: the save is hundreds of serial file writes.
        await asyncio.to_thread(
            persist_spec_save,
            eval=eval,
            eval_config=eval_config,
            single_turn_dataset=single_turn_dataset,
            spec=spec,
            batch_leaves=batch_leaves,
            batch_eval_inputs=batch_eval_inputs,
            reviewed_refs=reviewed_refs,
            reviewed_leaf_ids=reviewed_leaf_ids,
            golden_tag=golden_tag,
            spec_name=request.name,
        )

        return spec
