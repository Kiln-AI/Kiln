import hashlib
import json
from collections import defaultdict
from typing import Annotated, Any, Dict, List, Literal, Set, Tuple

from fastapi import FastAPI, HTTPException, Path, Query, Request
from pydantic import ValidationError
from fastapi.responses import StreamingResponse
from kiln_ai.adapters.eval.eval_runner import EvalRunner
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_ai.adapters.fine_tune.finetune_run_config_id import (
    finetune_from_finetune_run_config_id,
    finetune_run_config_id,
)
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.prompt_builders import prompt_builder_from_id
from kiln_ai.datamodel import BasePrompt, Task, TaskRun
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.dataset_filters import (
    DatasetFilterId,
    EvalInputFilterId,
    dataset_filter_from_id,
    eval_input_filter_from_id,
)
from kiln_ai.adapters.eval.base_eval import (
    DEFAULT_SYSTEM_PROMPT,
    build_default_llm_judge_prompt,
    materialize_llm_judge_properties,
)
from kiln_ai.adapters.eval.registry import v2_eval_adapter_from_config
from kiln_ai.adapters.eval.v2_eval_code_eval import (
    CodeEvalAdapter,
    add_code_trust,
    has_add_code_trust,
)
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalOutputScore,
    EvalRun,
    EvalScores,
    EvalSplitName,
    EvalTaskInput,
    EvalTemplateId,
    SkippedReason,
    V2EvalConfigProperties,
    validate_scores_against_output_scores,
)
from kiln_ai.datamodel.json_schema import string_to_json_key
from kiln_ai.datamodel.prompt_id import is_frozen_prompt
from kiln_ai.datamodel.prompt_type import generator_label
from kiln_ai.datamodel.provenance import KilnArtifactProvenance
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.spec import Spec, SpecStatus
from kiln_ai.datamodel.task import RunConfigProperties, TaskRunConfig
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.task_output import normalize_rating
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.git_sync_decorators import build_save_context, no_write_lock
from kiln_server.project_api import project_from_id
from kiln_server.provenance_api import validate_provenance_or_400
from kiln_server.statistics_lib import percentile
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, Field

from .correlation_calculator import (
    CorrelationCalculator,
    CorrelationResult,
    CorrelationScore,
)


def reusable_frozen_prompt_id(
    task: Task,
    project_id: ID_TYPE,
    prompt_text: str,
    cot_instructions: str | None,
) -> str | None:
    """Find an existing run config whose frozen prompt exactly matches the given
    content, so we can reuse it instead of creating a duplicate frozen prompt.

    Returns the frozen prompt id (task_run_config::...) of the match, or None if
    there's no match. If multiple match (legacy data created before dedup), the
    most recently created run config is used.
    """
    # Treat empty-string and missing chain-of-thought instructions as equivalent
    # so prompts dedupe regardless of how "no instructions" is represented.
    normalized_cot = cot_instructions or None
    matches = [
        run_config
        for run_config in task.run_configs(readonly=True)
        if run_config.prompt is not None
        and run_config.prompt.prompt == prompt_text
        and (run_config.prompt.chain_of_thought_instructions or None) == normalized_cot
    ]
    if not matches:
        return None
    most_recent = max(matches, key=lambda run_config: run_config.created_at)
    return f"task_run_config::{project_id}::{task.id}::{most_recent.id}"


def eval_from_id(project_id: str, task_id: str, eval_id: str) -> Eval:
    task = task_from_id(project_id, task_id)
    eval = Eval.from_id_and_parent_path(eval_id, task.path)
    if eval is not None:
        return eval

    raise HTTPException(
        status_code=404,
        detail=f"Eval not found. ID: {eval_id}",
    )


def split_filter_id_from_eval(eval: Eval, split: EvalSplitName) -> DatasetFilterId:
    """Resolve a split name to the eval's stored dataset filter id.

    422 when the eval has no filter configured for that split, or is an
    EvalInput-backed (V2) eval — splits are TaskRun dataset filters, which V2
    evals don't run against (rejected up front: the lazy migration mints
    train/val tag filters even on V2 evals, so train/val would otherwise
    resolve and then fail downstream). "train" and "val" can be unset on evals
    constructed without them; "test" resolves to eval_set_filter_id (its
    legacy name).
    """
    if eval.eval_input_filter_id is not None:
        raise HTTPException(
            status_code=422,
            detail=f"Eval '{eval.id}' is EvalInput-backed (V2); dataset splits are "
            "not supported for it.",
        )
    filter_id = eval.filter_id_for_split(split)
    if filter_id is None:
        # The field name matches the split for train/val; for test the backing
        # field is the legacy-named eval_set_filter_id.
        field_name = (
            "eval_set_filter_id" if split == "test" else f"{split}_set_filter_id"
        )
        raise HTTPException(
            status_code=422,
            detail=f"Eval '{eval.id}' has no {split} split configured (no {field_name}).",
        )
    return filter_id


def eval_config_from_id(
    project_id: str, task_id: str, eval_id: str, eval_config_id: str
) -> EvalConfig:
    eval = eval_from_id(project_id, task_id, eval_id)
    for config in eval.configs():
        if config.id == eval_config_id:
            return config

    raise HTTPException(
        status_code=404,
        detail=f"Eval config not found. ID: {eval_config_id}",
    )


def get_all_run_configs(project_id: str, task_id: str) -> list[TaskRunConfig]:
    """
    Returns all run configs for a task, including completed fine-tune run configs.
    Only includes fine-tunes that have a fine_tune_model_id (are completed and usable).
    """
    task = task_from_id(project_id, task_id)
    configs = task.run_configs()

    # Get run configs from finetunes and only include completed fine-tunes
    finetunes = task.finetunes()
    for finetune in finetunes:
        if finetune.run_config is not None and finetune.fine_tune_model_id is not None:
            configs.append(
                TaskRunConfig(
                    id=finetune_run_config_id(project_id, task_id, str(finetune.id)),
                    name=finetune.name,
                    description=finetune.description,
                    run_config_properties=finetune.run_config,
                    parent=task,  # special case, we need to reference the task model
                )
            )

    return configs


def task_run_config_from_id(
    project_id: str, task_id: str, run_config_id: str
) -> TaskRunConfig:
    task = task_from_id(project_id, task_id)
    for run_config in task.run_configs():
        if run_config.id == run_config_id:
            return run_config

    # special case for finetune run configs, it's inside the finetune model
    if run_config_id.startswith("finetune_run_config::"):
        finetune = finetune_from_finetune_run_config_id(run_config_id)
        if finetune.run_config is not None:
            return TaskRunConfig(
                id=finetune_run_config_id(project_id, task_id, str(finetune.id)),
                name=finetune.name,
                description=finetune.description,
                run_config_properties=finetune.run_config,
                parent=task,  # special case, we need to reference the task model
            )

    raise HTTPException(
        status_code=404,
        detail=f"Task run config not found. ID: {run_config_id}",
    )


async def run_eval_runner_with_status(eval_runner: EvalRunner) -> StreamingResponse:
    # Yields async messages designed to be used with server sent events (SSE)
    # https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
    async def event_generator():
        async for progress in eval_runner.run():
            data = {
                "progress": progress.complete,
                "total": progress.total,
                "errors": progress.errors,
            }
            yield f"data: {json.dumps(data)}\n\n"

        # Send the final complete message the app expects, and uses to stop listening
        yield "data: complete\n\n"

    return CancellableStreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
    )


class CreateEvaluatorRequest(BaseModel):
    """Request to create a new evaluator."""

    name: str = Field(description="The name of the evaluator.")
    description: str | None = Field(
        default=None, description="The description of the evaluator."
    )
    template: EvalTemplateId | None = Field(
        default=None, description="The eval template to use."
    )
    output_scores: list[EvalOutputScore] = Field(
        description="The scores this evaluator should produce."
    )
    eval_set_filter_id: DatasetFilterId = Field(
        description="The dataset filter for the eval set."
    )
    eval_configs_filter_id: DatasetFilterId | None = Field(
        default=None, description="The dataset filter for comparing eval configs."
    )
    template_properties: dict[str, str | float | int | bool] | None = Field(
        default=None, description="Template-specific properties."
    )
    evaluation_data_type: EvalDataType = Field(
        description="The type of task output to evaluate."
    )


class CreateEvalConfigRequest(BaseModel):
    """Request to create a new eval configuration."""

    name: str | None = Field(default=None, description="The name of the eval config.")
    type: EvalConfigType = Field(description="The type of eval config.")
    properties: dict[str, Any] = Field(
        description="Properties for the eval config, specific to the type."
    )
    model_name: str | None = Field(
        default=None,
        description="The model to use for evaluation. Required for LLM-based eval types.",
    )
    provider: ModelProviderName | None = Field(
        default=None,
        description="The provider of the evaluation model. Required for LLM-based eval types.",
    )
    provenance: KilnArtifactProvenance | None = Field(
        default=None,
        description="Provenance: why this eval config exists and what it was derived from.",
    )


class LlmJudgeBuilderInput(BaseModel):
    """Shared fields for llm_judge: model, provider, g_eval."""

    model_name: str = Field(description="The LLM model to use as judge.")
    provider: ModelProviderName = Field(description="The model provider.")
    g_eval: bool = Field(description="Whether to use G-Eval logprob scoring.")
    judge_prompt: str | None = Field(
        default=None,
        description="Override the judge prompt template. If unset, the server assembles a rich default from the eval's task and spec.",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Override the judge system prompt. Defaults to 'You are an evaluator.'",
    )


class DefaultLlmJudgePromptResponse(BaseModel):
    """Response from the default LLM judge prompt endpoint."""

    judge_prompt: str
    system_prompt: str


class CreateLlmJudgeConfigRequest(LlmJudgeBuilderInput):
    """Request to create a V2 llm_judge eval config with server-baked template."""

    name: str | None = Field(default=None, description="The name of the eval config.")
    reference_keys: list[str] = Field(
        default_factory=list,
        description="Reference data keys this judge needs (captured from test).",
    )


class TestV2EvalRequest(BaseModel):
    """Request to test-run a V2 eval config without persisting."""

    properties: V2EvalConfigProperties | None = Field(
        default=None,
        description="The V2 eval config properties to test. Required unless llm_judge_builder_input is set.",
    )
    eval_input: EvalTaskInput = Field(description="The input to evaluate.")
    llm_judge_builder_input: LlmJudgeBuilderInput | None = Field(
        default=None,
        description="Builder input for llm_judge; when set, the server bakes the full properties from the eval's output_scores.",
    )


class TestV2EvalResponse(BaseModel):
    """Response from a test-run of a V2 eval."""

    scores: EvalScores = Field(default_factory=dict)
    skipped_reason: str | None = None
    skipped_detail: str | None = None
    score_range_errors: list[str] | None = None
    intermediate_outputs: dict[str, str] | None = None


class CodeTrustResponse(BaseModel):
    """Response indicating whether code is trusted for a project in this session."""

    trusted: bool


class CreateTaskRunConfigRequest(BaseModel):
    """Request to create a new run config for eval."""

    name: str | None = Field(default=None, description="The name of the run config.")
    description: str | None = Field(
        default=None, description="The description of the run config."
    )
    run_config_properties: RunConfigProperties = Field(
        description="The run configuration properties."
    )
    provenance: KilnArtifactProvenance | None = Field(
        default=None,
        description="Provenance: why this run config exists and what it was derived from.",
    )


class UpdateRunConfigRequest(BaseModel):
    """Request to update a run config."""

    name: str | None = Field(default=None, description="The updated name.")
    starred: bool | None = Field(
        default=None, description="The updated starred status."
    )
    prompt_name: str | None = Field(
        default=None, description="The updated prompt name."
    )


class RunEvalConfigRequest(BaseModel):
    """Request to run an eval with specific run configs."""

    run_config_ids: list[str] = Field(description="The run config IDs to evaluate.")


class ScoreSummary(BaseModel):
    """Summary of scores for an eval run."""

    mean_score: float | None = Field(
        description="The mean score across all used runs. None when n_used == 0."
    )
    # Distribution fields. Optional/defaulted so older stored payloads and
    # existing API consumers keep working — the mean is unchanged. Numeric
    # (custom-type) scores like tool-call counts or per-turn latency are
    # heavily right-skewed, where the mean hides the tail that drives cost.
    min_score: float | None = Field(
        default=None,
        description="The lowest score across all used runs. None when n_used == 0.",
    )
    p25_score: float | None = Field(
        default=None,
        description="The 25th-percentile score across all used runs. None when n_used == 0.",
    )
    median_score: float | None = Field(
        default=None,
        description="The median (50th-percentile) score across all used runs. None when n_used == 0.",
    )
    p75_score: float | None = Field(
        default=None,
        description="The 75th-percentile score across all used runs. None when n_used == 0.",
    )
    p90_score: float | None = Field(
        default=None,
        description="The 90th-percentile score across all used runs. None when n_used == 0.",
    )
    max_score: float | None = Field(
        default=None,
        description="The highest score across all used runs. None when n_used == 0.",
    )
    n_used: int = Field(
        description="Number of EvalRuns with all expected scores and not skipped."
    )
    n_excluded: int = Field(
        description="Number of EvalRuns excluded due to skipped_reason."
    )


class MeanUsage(BaseModel):
    """Average token usage across eval runs."""

    mean_input_tokens: float | None = Field(
        default=None, description="Average input tokens per run."
    )
    mean_output_tokens: float | None = Field(
        default=None, description="Average output tokens per run."
    )
    mean_total_tokens: float | None = Field(
        default=None, description="Average total tokens per run."
    )
    mean_cost: float | None = Field(
        default=None, description="Average cost per run in USD."
    )
    mean_total_llm_latency_ms: float | None = Field(
        default=None,
        description="Average total LLM latency per run in milliseconds.",
    )


class EvalRunResult(BaseModel):
    """Results of an eval run including the eval and run config."""

    results: List[EvalRun] = Field(description="The individual eval run results.")
    eval: Eval = Field(description="The parent eval.")
    eval_config: EvalConfig = Field(description="The eval config used.")
    run_config: TaskRunConfig = Field(description="The run config used.")


class UpdateFavouriteRequest(BaseModel):
    """Request to update the favourite status of an eval."""

    favourite: bool = Field(description="Whether the eval is a favourite.")


class UpdateEvalRequest(BaseModel):
    """Request to update an eval."""

    name: str | None = Field(default=None, description="The updated name.")
    description: str | None = Field(
        default=None, description="The updated description."
    )
    train_set_filter_id: str | None = Field(
        default=None, description="The updated train set filter ID."
    )


class EvalProgress(BaseModel):
    """Progress information for an eval."""

    dataset_size: int = Field(description="The total size of the eval dataset.")
    golden_dataset_size: int = Field(
        description="The total size of the golden dataset."
    )
    golden_dataset_not_rated_count: int = Field(
        description="Number of unrated golden dataset items."
    )
    golden_dataset_partially_rated_count: int = Field(
        description="Number of partially rated golden dataset items."
    )
    golden_dataset_fully_rated_count: int = Field(
        description="Number of fully rated golden dataset items."
    )
    train_dataset_size: int = Field(description="The total size of the train dataset.")
    current_eval_method: EvalConfig | None = Field(
        default=None, description="The currently selected eval config."
    )


class EvalResultSummary(BaseModel):
    """Summary of eval results across run configs."""

    results: Dict[ID_TYPE, Dict[str, ScoreSummary]] = Field(
        description="Scores keyed by run_config_id then output_score_id."
    )
    run_config_percent_complete: Dict[ID_TYPE, float] = Field(
        description="Percent of dataset processed per run config."
    )
    dataset_size: int = Field(description="Total size of the eval dataset.")


class EvalResultsSummaryEvalInfo(BaseModel):
    """Metadata for a single eval within eval results summary."""

    name: str = Field(description="The eval name.")
    default_judge_config_id: ID_TYPE | None = Field(
        description="The default judge config ID for this eval, if any."
    )
    dataset_size: int = Field(
        description="Number of items in the slice being summarized: the eval's "
        "own set, or the requested split's."
    )
    output_score_keys: list[str] = Field(
        description="The output score keys for this eval."
    )
    declared_splits: list[str] = Field(
        default_factory=list,
        description="Named dataset splits this eval has a filter for, of "
        "'test', 'train', 'val'. An eval missing the split being viewed "
        "contributes no results to it.",
    )
    split_available: bool = Field(
        default=True,
        description="Whether the requested split resolved for this eval. False "
        "means its cells are absent because it has no such split, not because "
        "nothing has been run.",
    )


class EvalResultsSummaryRunConfigInfo(BaseModel):
    """Metadata for a run config within eval results summary."""

    name: str = Field(description="The run config name.")


class EvalResultsSummaryResultCell(BaseModel):
    """Results for a single (eval, run_config) cell."""

    mean_scores: Dict[str, float] = Field(
        description="Mean scores keyed by output_score_key."
    )
    percent_complete: float = Field(
        description="Percent of dataset processed for this run config."
    )
    n_used_by_score_key: Dict[str, int] = Field(
        default_factory=dict,
        description="How many runs each mean is over, keyed by "
        "output_score_key. A mean over a 25-item train split and one over a "
        "150-item test set are not the same claim, and the number is the only "
        "thing that says so.",
    )


class EvalResultsSummaryResponse(BaseModel):
    """Aggregated eval results across all evals for a task."""

    evals_by_id: Dict[ID_TYPE, EvalResultsSummaryEvalInfo] = Field(
        description="Eval metadata keyed by eval ID."
    )
    run_configs_by_id: Dict[ID_TYPE, EvalResultsSummaryRunConfigInfo] = Field(
        description="Run config metadata keyed by run config ID."
    )
    scores_by_run_config_by_eval: Dict[
        ID_TYPE, Dict[ID_TYPE, EvalResultsSummaryResultCell]
    ] = Field(description="Results keyed by run config ID then eval ID.")
    split: str | None = Field(
        default=None,
        description="The split these results were scoped to, echoed back. None "
        "means the request did not ask for one and got each eval's own set.",
    )


class EvalConfigCompareSummary(BaseModel):
    """Summary comparing eval configs against human ratings."""

    results: Dict[ID_TYPE, Dict[str, CorrelationResult]] = Field(
        description="Correlation results keyed by eval_config_id then output_score_id."
    )
    eval_config_percent_complete: Dict[ID_TYPE, float] = Field(
        description="Percent of dataset processed per eval config."
    )
    dataset_size: int = Field(
        description="Total size of the eval config comparison dataset."
    )
    fully_rated_count: int = Field(description="Number of fully rated dataset items.")
    partially_rated_count: int = Field(
        description="Number of partially rated dataset items."
    )
    not_rated_count: int = Field(description="Number of unrated dataset items.")


class EvalConfigResult(BaseModel):
    """Results for a single eval config."""

    eval_config_id: ID_TYPE = Field(description="The eval config ID.")
    results: Dict[str, ScoreSummary | None] = Field(
        description="Scores keyed by output_score_id. None when no data."
    )
    percent_complete: float = Field(description="Percent of the dataset processed.")
    n_excluded: int = Field(
        default=0,
        description="Number of EvalRuns excluded due to skipped_reason.",
    )


class RunConfigEvalResult(BaseModel):
    """Eval results for a specific run config."""

    eval_id: ID_TYPE = Field(description="The unique identifier of the eval.")
    eval_name: str = Field(description="The human-readable name of the eval.")
    dataset_size: int = Field(
        description="Number of items in the slice being reported: the eval's "
        "own set, or the requested split's."
    )
    eval_config_result: EvalConfigResult | None = Field(
        default=None, description="The eval config results, if available."
    )
    missing_default_eval_config: bool = Field(
        description="Whether the default eval config is missing."
    )
    spec_id: ID_TYPE | None = Field(
        default=None, description="The associated spec ID, if any."
    )
    declared_splits: list[str] = Field(
        default_factory=list,
        description="Named dataset splits this eval has a filter for, of "
        "'test', 'train', 'val'.",
    )
    split_available: bool = Field(
        default=True,
        description="Whether the requested split resolved for this eval. False "
        "means no results for it, because the eval has no such split.",
    )


class RunConfigEvalScoresSummary(BaseModel):
    """Summary of all eval scores for a run config."""

    eval_results: List[RunConfigEvalResult] = Field(
        description="Eval results for each eval."
    )
    mean_usage: MeanUsage | None = Field(
        default=None, description="Average usage statistics across eval runs."
    )
    split: str | None = Field(
        default=None,
        description="The split these results were scoped to, echoed back. None "
        "means the request did not ask for one and got each eval's own set.",
    )
    n_eval_runs: int = Field(
        default=0,
        description="How many eval runs the usage averages are over, after "
        "split scoping. Zero means the usage is absent, not zero.",
    )


class EvalRunIndexRow(BaseModel):
    """One eval run, stripped to what a comparison basis needs.

    The full EvalRun carries its input, its output and the whole task run
    trace, which is why /results is fetched one cell at a time by the
    inspector. This is the same run with all of that dropped: the item it
    scored, the scores, and the usage the run cost. Small enough to fetch every
    row of every eval for a dozen run configs at once, which is what matching
    run configs on the conversations they actually share requires.
    """

    item_id: ID_TYPE = Field(
        description="The item this run scored: an EvalInput id on a V2 eval, a "
        "TaskRun (dataset) id on a V1 one. Unique within an eval's rows."
    )
    eval_run_id: ID_TYPE = Field(
        description="The EvalRun this row is. One record, one row - not an "
        "identity for the conversation behind it, which is what execution_id is."
    )
    execution_id: str = Field(
        description="Which CONVERSATION this row's scores were computed over. "
        "Equal across two rows exactly when they scored the same run of the "
        "task, so a caller can join rows from different evals and know it is "
        "reading one execution rather than two."
    )
    scores: Dict[str, float] = Field(
        default_factory=dict,
        description="The run's scores, keyed by output_score_key, exactly as "
        "stored. A key an eval declares can be absent here, the same way it is "
        "absent from the per-key counts in the summary.",
    )
    input_tokens: float | None = Field(
        default=None, description="Input tokens this run used. None when unrecorded."
    )
    output_tokens: float | None = Field(
        default=None, description="Output tokens this run used. None when unrecorded."
    )
    total_tokens: float | None = Field(
        default=None, description="Total tokens this run used. None when unrecorded."
    )
    cost: float | None = Field(
        default=None, description="Cost of this run in USD. None when unrecorded."
    )
    total_llm_latency_ms: float | None = Field(
        default=None,
        description="End-to-end LLM latency of this run in ms. None when unrecorded.",
    )


class EvalRunIndexEval(BaseModel):
    """One eval's rows for the requested run config."""

    eval_id: ID_TYPE = Field(description="The unique identifier of the eval.")
    eval_config_id: ID_TYPE = Field(
        description="The judge config these rows came from: the eval's current "
        "default, the same one every other compare surface reads."
    )
    rows: List[EvalRunIndexRow] = Field(
        description="The run config's non-skipped runs under this eval, one per "
        "item. Empty when it has never been run against this split."
    )


class EvalRunIndexResponse(BaseModel):
    """Per-run rows for one run config, across every eval on the task."""

    evals: List[EvalRunIndexEval] = Field(
        description="One entry per eval that has a default judge config and "
        "resolves the requested split. An eval missing either is omitted "
        "rather than reported: this payload feeds a comparison basis, and an "
        "eval that cannot supply rows cannot contribute to one. The summary "
        "endpoints are where an eval's absence is explained."
    )
    split: str | None = Field(
        default=None,
        description="The split these rows were scoped to, echoed back. None "
        "means the request did not ask for one and got each eval's own set.",
    )


def dataset_ids_in_filter(
    task: Task, filter_id: DatasetFilterId, readonly: bool
) -> Set[ID_TYPE]:
    # Fetch all the dataset items IDs in a filter
    filter = dataset_filter_from_id(filter_id)
    return {run.id for run in task.runs(readonly=readonly) if filter(run)}


def runs_in_filter(
    task: Task, filter_id: DatasetFilterId, readonly: bool
) -> list[TaskRun]:
    # Fetch all the dataset items IDs in a filter
    filter = dataset_filter_from_id(filter_id)
    return [run for run in task.runs(readonly=readonly) if filter(run)]


def eval_input_ids_in_filter(
    task: Task, filter_id: EvalInputFilterId, readonly: bool
) -> Set[ID_TYPE]:
    # Fetch all the EvalInput item IDs in a filter
    filter = eval_input_filter_from_id(filter_id)
    return {
        eval_input.id
        for eval_input in task.eval_inputs(readonly=readonly)
        if filter(eval_input)
    }


def expected_item_ids_for_eval(
    task: Task, eval: Eval, readonly: bool
) -> Set[ID_TYPE] | None:
    """IDs of the items an eval is expected to score. An eval's slice is either
    TaskRun-typed (eval_set_filter_id) or EvalInput-typed (eval_input_filter_id);
    its EvalRuns key on dataset_id or eval_input_id respectively. Returns None
    when neither filter is set (Eval validates exactly one, so only reachable
    for hand-edited files)."""
    if eval.eval_set_filter_id is not None:
        return dataset_ids_in_filter(task, eval.eval_set_filter_id, readonly=readonly)
    if eval.eval_input_filter_id is not None:
        return eval_input_ids_in_filter(
            task, eval.eval_input_filter_id, readonly=readonly
        )
    return None


def specs_by_eval_id(task: Task, readonly: bool = True) -> Dict[ID_TYPE, Spec]:
    """The spec each eval belongs to, keyed by eval id.

    One scan of the task's specs, so a caller looping over every eval reads the
    spec's status and id off a map rather than re-scanning per eval (which is
    what Eval.associated_spec does). Legacy evals predate specs and are simply
    absent from the map.
    """
    return {
        spec.eval_id: spec for spec in task.specs(readonly=readonly) if spec.eval_id
    }


def eval_run_item_id(eval_run: EvalRun) -> ID_TYPE:
    # The item an EvalRun scored: EvalRun validates exactly one of dataset_id
    # (TaskRun source) or eval_input_id (EvalInput source) is set.
    return (
        eval_run.dataset_id
        if eval_run.dataset_id is not None
        else eval_run.eval_input_id
    )


def eval_run_execution_id(eval_run: EvalRun) -> str:
    """Which CONVERSATION an EvalRun's scores were computed over.

    An item id is NOT this. Two evals can hold a row for the same item under
    the same run config and mean two different runs of the task: trace reuse
    makes them one conversation judged twice, but a second drive - a resample,
    or two jobs racing - makes them two. A caller that joins rows across evals
    by item id (say, to read a metrics eval's tool_calls for a judge's item)
    reads the wrong conversation's number whenever it is the second case, and
    has no way to tell from the payload which case it got.

    Nothing stored on the record is that identity:

    - `drive_fingerprint` is the drive's INPUTS (drive config + run config +
      scenario), which is what makes reuse safe to look up. It is equal by
      construction across two independent drives of the same scenario.
      Measured on a real task: 756 of 756 cross-eval (config, item) pairs
      shared a fingerprint while 85 of them held demonstrably different
      conversations.
    - there is no task-run id to borrow. A V2 run stores its conversation
      inline as `task_run_trace` and a V1 run stores its output inline; neither
      points at a persisted TaskRun.

    So the identity is the conversation's own content: a hash of the stored
    trace. Rows that reused a trace hash equal, rows from separate drives do
    not, and the only cost is a digest over a string already in memory.

    A run with no trace (V1 evals, final-answer evals) falls back to the
    record's own id, which makes every such row its own execution. That is the
    conservative direction: a cross-eval join finds no match and reports a
    missing value instead of quietly reading a different run's number.
    """
    trace = eval_run.task_run_trace
    if trace is None:
        return f"run:{eval_run.id}"
    return f"trace:{hashlib.sha256(trace.encode('utf-8')).hexdigest()}"


# ---------------------------------------------------------------------------
# Reading a run config's results one dataset split at a time.
#
# An eval's own filter (eval_set_filter_id, or eval_input_filter_id on V2) is
# its TEST set, and until now it was the only slice the compare views could
# read: every summary scoped its runs to expected_item_ids_for_eval and dropped
# the rest. But a run config is usually iterated against the TRAIN split and
# only measured on test at the end, so the work that produced a config was
# invisible on the page that compares configs - a config with 25 train runs and
# no test runs rendered as "no score", indistinguishable from one nobody ever
# ran.
#
# The splits are already in the datamodel: train_set_filter_id and
# val_set_filter_id sit beside the test filter on every Eval. What is NOT in
# the datamodel is which split an EvalRun belongs to - it records the item it
# scored, not the slice that selected it - so a split is resolved the same way
# it is at run time: by asking which items the split's filter selects, and
# keeping the runs that scored one of them.
#
# This is a READ-side vocabulary and deliberately not EvalSplitName, the one
# EvalJobParams uses to run an eval. "all" is meaningful here (show every run
# that exists, whatever selected it) and meaningless there (you cannot run
# "all" - EvalRunner needs one filter), and V2 evals answer here (their splits
# are EvalInput tag filters) where they 422 there (EvalRunner cannot run a
# TaskRun filter against an EvalInput dataset - see split_filter_id_from_eval).
# ---------------------------------------------------------------------------

EvalSplitQuery = Literal["train", "val", "test", "all"]


def eval_uses_eval_inputs(eval: Eval) -> bool:
    """Whether an eval's items are EvalInputs (V2) rather than TaskRuns (V1).

    Same precedence as expected_item_ids_for_eval: the TaskRun filter wins if
    both are somehow set, so the two can never disagree about which store an
    eval's item ids come from."""
    return eval.eval_set_filter_id is None and eval.eval_input_filter_id is not None


def split_item_ids_for_eval(
    task: Task, eval: Eval, split: EvalSplitName, readonly: bool
) -> Set[ID_TYPE] | None:
    """The items in one of an eval's named splits, or None when the eval has no
    usable filter for it.

    "test" is the eval's own slice, so it goes through expected_item_ids_for_eval
    unchanged - that is what an omitted split has always meant.

    train/val come from the eval's own fields, resolved against the store the
    eval's items live in. The fields are shared between V1 and V2 (a tag filter
    reads the same either way) but the STORE is not, so the same id is resolved
    against EvalInputs for a V2 eval and TaskRuns for a V1 one. Filters that
    only the TaskRun grammar accepts (high_rating, multi_filter::, ...) raise
    on the EvalInput side; that is "no such split", not an error, because a
    train filter nobody set for this eval's source is exactly the case the
    caller has to degrade over."""
    if split == "test":
        return expected_item_ids_for_eval(task, eval, readonly=readonly)

    filter_id = eval.filter_id_for_split(split)
    if filter_id is None:
        return None
    try:
        if eval_uses_eval_inputs(eval):
            return eval_input_ids_in_filter(task, filter_id, readonly=readonly)
        return dataset_ids_in_filter(task, filter_id, readonly=readonly)
    except ValueError:
        return None


def scored_item_ids(eval_config: EvalConfig) -> Set[ID_TYPE]:
    """Every item any run config has scored under this judge config."""
    return {
        eval_run_item_id(eval_run)
        for eval_run in eval_config.runs(readonly=True)
        if eval_run.task_run_config_id is not None
    }


class SplitItemResolver:
    """One request's answer to "which items are in split S of eval E".

    Memoized per (source, filter id): the eval_set and eval_input filters share
    the tag:: grammar but select different stores, so the filter id alone is
    not a safe cache key. Worth having because a task's evals routinely share a
    filter, and each resolution walks every TaskRun or EvalInput in the task.

    Resolution goes through the module-level dataset_ids_in_filter /
    eval_input_ids_in_filter rather than reimplementing them, so a caller that
    patches those (tests do) still sees every call."""

    def __init__(self, task: Task, readonly: bool = True):
        self.task = task
        self.readonly = readonly
        self._cache: Dict[Tuple[str, str], Set[ID_TYPE] | None] = {}

    def items_for_split(self, eval: Eval, split: EvalSplitName) -> Set[ID_TYPE] | None:
        source = "eval_input" if eval_uses_eval_inputs(eval) else "task_run"
        if split == "test":
            filter_id = eval.eval_set_filter_id or eval.eval_input_filter_id
        else:
            filter_id = eval.filter_id_for_split(split)
        key = (source, str(filter_id))
        if key not in self._cache:
            self._cache[key] = split_item_ids_for_eval(
                self.task, eval, split, readonly=self.readonly
            )
        return self._cache[key]

    def items_for_query(
        self, eval: Eval, eval_config: EvalConfig | None, split: EvalSplitQuery | None
    ) -> Set[ID_TYPE] | None:
        """The item set a split query scopes an eval to, or None when this eval
        has no such split.

        None and "test" are the same request - the eval's own slice - so an
        omitted parameter is byte-identical to what every caller got before
        splits existed.

        "all" is every item that has been scored under this judge config, plus
        the eval's own slice. Not the union of the three splits: runs exist
        against items that are in none of them (an item can drift out of a
        filter, or have been scored under a filter since changed), and an "all"
        that hid those would be smaller than the sum of its parts. Including
        the test slice keeps the denominator the declared universe, so a config
        that only ever ran train reads as partially complete rather than 100%."""
        if split is None or split == "test":
            return self.items_for_split(eval, "test")
        if split == "all":
            expected = self.items_for_split(eval, "test") or set()
            if eval_config is None:
                return expected
            return expected | scored_item_ids(eval_config)
        return self.items_for_split(eval, split)

    def declared_splits(self, eval: Eval) -> List[str]:
        """The named splits this eval declares a filter for, in reading order.

        Declared, not resolved: a filter is one field read, where resolving it
        is a walk of the task's items, and this is reported for every eval on
        every request whatever split is being viewed. A declared split can
        still come back empty (nothing tagged into it yet) or unusable (a
        TaskRun-only filter on a V2 eval); both then show as a split with no
        results rather than as an absent one, which is the same thing the
        reader can act on - there is nothing to see either way."""
        splits: List[str] = []
        if eval.eval_set_filter_id is not None or eval.eval_input_filter_id is not None:
            splits.append("test")
        for split in ("train", "val"):
            if eval.filter_id_for_split(split) is not None:
                splits.append(split)
        return splits


def build_score_key_to_task_requirement_id(task: Task) -> Dict[str, ID_TYPE]:
    # Create a map of score_key -> Task requirement ID
    score_key_to_task_requirement_id: Dict[str, ID_TYPE] = {}

    for task_requirement in task.requirements:
        score_key = string_to_json_key(task_requirement.name)
        score_key_to_task_requirement_id[score_key] = task_requirement.id
    return score_key_to_task_requirement_id


def human_score_from_task_run(
    task_run: TaskRun,
    score: EvalOutputScore,
    score_key_to_task_requirement_id: Dict[str, ID_TYPE],
) -> float | None:
    if not task_run.output.rating:
        return None
    score_key = score.json_key()

    # Overall rating
    if score_key == "overall_rating":
        return task_run.output.rating.value

    # Task requirement ratings. A requirement whose name matches the score
    # key may still be unrated — fall through to the named lookup rather
    # than letting the name collision hide a named rating for this score.
    req_id = score_key_to_task_requirement_id.get(score_key, None)
    if req_id:
        req_rating = task_run.output.rating.requirement_ratings.get(req_id, None)
        if req_rating is not None:
            return req_rating.value

    # Named ratings
    named_score_id = f"named::{score.name}"
    named_rating = task_run.output.rating.requirement_ratings.get(named_score_id, None)
    if named_rating is not None:
        return named_rating.value
    return None


def count_human_evals(
    items: List[TaskRun],
    eval: Eval,
    score_key_to_task_requirement_id: Dict[str, ID_TYPE],
) -> Tuple[int, int, int]:
    # Track how often we are missing human evals in dataset items
    fully_rated_count: int = 0
    partially_rated_count: int = 0
    not_rated_count: int = 0
    for dataset_item in items:
        has_all_scores = True
        has_any_scores = False
        for output_score in eval.output_scores:
            # Humans can't rate custom metrics (no rating UI for them), so
            # counting them would pin every item at "partially rated".
            if output_score.type == TaskOutputRatingType.custom:
                continue
            score = human_score_from_task_run(
                dataset_item, output_score, score_key_to_task_requirement_id
            )
            if score is None:
                has_all_scores = False
            else:
                has_any_scores = True

        if not has_any_scores:
            not_rated_count += 1
        elif has_all_scores:
            fully_rated_count += 1
        else:
            partially_rated_count += 1

    return fully_rated_count, partially_rated_count, not_rated_count


def score_summary_from_values(values: list[float], n_excluded: int) -> ScoreSummary:
    """Build a ScoreSummary from the raw per-run scores of one output score key.

    `values` must already exclude skipped runs and runs missing this score —
    the caller does that filtering, exactly as it always has for the mean.

    Percentiles use linear interpolation between the two nearest order
    statistics (`statistics_lib.percentile`), matching the numpy.percentile /
    statistics.quantiles(method="inclusive") default. So an even-length list's
    median is the average of the two middle values, and p90 of a short list is
    interpolated rather than snapped to an existing datum. This is the only
    percentile definition used anywhere in eval aggregation — do not mix in
    another.

    Empty `values` yields None for every statistic (never 0.0, which would read
    downstream as a real datum rather than "no data").
    """
    count = len(values)
    if count == 0:
        return ScoreSummary(mean_score=None, n_used=0, n_excluded=n_excluded)
    return ScoreSummary(
        mean_score=sum(values) / count,
        min_score=min(values),
        p25_score=percentile(values, 25),
        median_score=percentile(values, 50),
        p75_score=percentile(values, 75),
        p90_score=percentile(values, 90),
        max_score=max(values),
        n_used=count,
        n_excluded=n_excluded,
    )


def compute_score_summary(
    eval: Eval,
    eval_config: EvalConfig,
    task_run_configs: list[TaskRunConfig],
    expected_item_ids: set[ID_TYPE],
) -> EvalResultSummary:
    """Aggregate an eval config's runs per run config. expected_item_ids are
    TaskRun IDs or EvalInput IDs depending on the eval's slice source (see
    expected_item_ids_for_eval); runs key on the matching EvalRun field."""
    if len(expected_item_ids) == 0:
        return EvalResultSummary(
            results={},
            run_config_percent_complete={},
            dataset_size=0,
        )

    remaining_expected_item_ids: Dict[ID_TYPE, Set[ID_TYPE]] = {
        run_config.id: set(expected_item_ids) for run_config in task_run_configs
    }
    partial_incomplete_counts: Dict[ID_TYPE, int] = {
        run_config.id: 0 for run_config in task_run_configs
    }

    # run_config_id -> output_score_json_key -> the individual scores, kept as a
    # list (not a running total) so the summary can report percentiles as well
    # as the mean.
    score_values: Dict[ID_TYPE, Dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    excluded_counts: Dict[ID_TYPE, int] = defaultdict(int)

    for eval_run in eval_config.runs(readonly=True):
        if eval_run.task_run_config_id is None:
            continue
        run_config_id = eval_run.task_run_config_id

        if run_config_id not in remaining_expected_item_ids:
            continue
        item_id = eval_run_item_id(eval_run)
        if item_id not in remaining_expected_item_ids[run_config_id]:
            continue
        else:
            remaining_expected_item_ids[run_config_id].remove(item_id)

        if eval_run.skipped_reason is not None:
            excluded_counts[run_config_id] += 1
            _ = score_values[run_config_id]
            continue

        incomplete = False
        # Ensure this run_config_id has an entry even if no scores match
        _ = score_values[run_config_id]
        for output_score in eval.output_scores:
            score_key = output_score.json_key()
            if score_key in eval_run.scores:
                score_values[run_config_id][score_key].append(
                    eval_run.scores[score_key]
                )
            else:
                incomplete = True

        if incomplete:
            partial_incomplete_counts[run_config_id] += 1

    all_score_keys = [os.json_key() for os in eval.output_scores]

    results: Dict[ID_TYPE, Dict[str, ScoreSummary]] = {}
    for run_config_id, output_scores in score_values.items():
        results[run_config_id] = {}
        n_excluded = excluded_counts[run_config_id]
        for score_key in all_score_keys:
            values = output_scores.get(score_key, [])
            if len(values) > 0 or n_excluded > 0:
                results[run_config_id][score_key] = score_summary_from_values(
                    values, n_excluded
                )

    run_config_percent_complete: Dict[ID_TYPE, float] = {}
    for run_config in task_run_configs:
        n_excluded = excluded_counts[run_config.id]
        incomplete_count = partial_incomplete_counts[run_config.id] + len(
            remaining_expected_item_ids[run_config.id]
        )
        n_processed = len(expected_item_ids) - incomplete_count
        percent_complete = (n_processed) / len(expected_item_ids)
        run_config_percent_complete[run_config.id] = percent_complete

    return EvalResultSummary(
        results=results,
        run_config_percent_complete=run_config_percent_complete,
        dataset_size=len(expected_item_ids),
    )


def connect_evals_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/create_evaluator",
        summary="Create Evaluator",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_evaluator(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        request: CreateEvaluatorRequest,
    ) -> Eval:
        task = task_from_id(project_id, task_id)
        eval = Eval(
            name=request.name,
            description=request.description,
            template=request.template,
            output_scores=request.output_scores,
            eval_set_filter_id=request.eval_set_filter_id,
            eval_configs_filter_id=request.eval_configs_filter_id,
            template_properties=request.template_properties,
            evaluation_data_type=request.evaluation_data_type,
            parent=task,
        )
        eval.save_to_file()
        return eval

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs",
        summary="List Run Configs",
        tags=["Run Configs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_run_configs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> list[TaskRunConfig]:
        return get_all_run_configs(project_id, task_id)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
        summary="Get Eval",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
    ) -> Eval:
        return eval_from_id(project_id, task_id, eval_id)

    @app.delete(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
        summary="Delete Eval",
        tags=["Evals"],
        openapi_extra=DENY_AGENT,
    )
    async def delete_eval(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
    ) -> None:
        eval = eval_from_id(project_id, task_id, eval_id)
        eval.delete()

    @app.patch(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
        summary="Update Eval",
        tags=["Evals"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to edit eval? Ensure you backup your project before allowing agentic edits."
        ),
    )
    async def update_eval(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        request: UpdateEvalRequest,
    ) -> Eval:
        eval = eval_from_id(project_id, task_id, eval_id)

        if request.name is not None:
            eval.name = request.name
        if request.description is not None:
            eval.description = request.description

        # legacy evals (not created with Specs) do not have a train set filter, but we need one
        # for some features such as prompt optimization
        if request.train_set_filter_id is not None:
            # if the eval already has a train set filter, we do not allow changing it because it
            # would make comparing results before and after the change very confusing
            if eval.train_set_filter_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Train set filter is already set and cannot be changed. Please create a new eval if you need a different train set.",
                )
            eval.train_set_filter_id = request.train_set_filter_id

        eval.save_to_file()
        return eval

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals",
        summary="List Evals",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_evals(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> list[Eval]:
        """List all evals for a task."""
        task = task_from_id(project_id, task_id)
        return task.evals()

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_configs",
        summary="List Eval Configs",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval_configs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
    ) -> list[EvalConfig]:
        eval = eval_from_id(project_id, task_id, eval_id)
        return eval.configs()

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}",
        summary="Get Eval Config",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval_config(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        eval_config_id: Annotated[
            str, Path(description="The unique identifier of the eval configuration.")
        ],
    ) -> EvalConfig:
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
        return eval_config

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs",
        summary="Create Run Config",
        tags=["Run Configs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_task_run_config(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        request: CreateTaskRunConfigRequest,
    ) -> TaskRunConfig:
        task = task_from_id(project_id, task_id)
        name = request.name or generate_memorable_name()

        parent_project = task.parent_project()
        if parent_project is None:
            raise HTTPException(
                status_code=400,
                detail="Task must have a parent project.",
            )

        frozen_prompt: BasePrompt | None = None
        reused_frozen_prompt_id: str | None = None
        run_config_properties = request.run_config_properties
        if isinstance(run_config_properties, KilnAgentRunConfigProperties):
            prompt_id = run_config_properties.prompt_id
            if not is_frozen_prompt(prompt_id):
                # For dynamic prompts, we "freeze" a copy of this prompt into the task run config so we don't accidentally invalidate evals if the user changes something that impacts the prompt (example: changing data for multi-shot, or changing task for basic-prompt)
                # We then point the task_run_config.run_properties.prompt_id to this frozen prompt
                prompt_builder = prompt_builder_from_id(prompt_id, task)
                prompt_text = prompt_builder.build_base_prompt()
                cot_instructions = prompt_builder.chain_of_thought_prompt()
                # Reuse an existing frozen prompt with identical content instead of
                # creating a duplicate, to avoid cluttering the prompts list.
                reused_frozen_prompt_id = reusable_frozen_prompt_id(
                    task, parent_project.id, prompt_text, cot_instructions
                )
                if reused_frozen_prompt_id is None:
                    # Bake the source prompt's type into the name (e.g.
                    # "Gusty Forest - Basic (Zero Shot)") so it's identifiable
                    # without resolving the generator at render time.
                    label = generator_label(prompt_id)
                    memorable_name = generate_memorable_name()
                    prompt_name = (
                        f"{memorable_name} - {label}" if label else memorable_name
                    )
                    frozen_prompt = BasePrompt(
                        name=prompt_name,
                        description=f"Frozen copy of prompt '{prompt_id}'.",
                        generator_id=prompt_id,
                        prompt=prompt_text,
                        chain_of_thought_instructions=cot_instructions,
                    )
        task_run_config = TaskRunConfig(
            parent=task,
            name=name,
            run_config_properties=run_config_properties,
            description=request.description,
            prompt=frozen_prompt,
            provenance=request.provenance,
        )
        validate_provenance_or_400(
            task_run_config.provenance,
            task_run_config.id,
            TaskRunConfig,
            task.path,
        )
        if isinstance(
            task_run_config.run_config_properties, KilnAgentRunConfigProperties
        ):
            if frozen_prompt is not None:
                # Set after, because the ID isn't known until the TaskRunConfig is created
                task_run_config.run_config_properties.prompt_id = f"task_run_config::{parent_project.id}::{task.id}::{task_run_config.id}"
            elif reused_frozen_prompt_id is not None:
                # Point at the existing frozen prompt we're reusing
                task_run_config.run_config_properties.prompt_id = (
                    reused_frozen_prompt_id
                )
        task_run_config.save_to_file()
        return task_run_config

    @app.patch(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}",
        summary="Update Run Config",
        tags=["Run Configs"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to edit run config? Ensure you backup your project before allowing agentic edits."
        ),
    )
    async def update_run_config(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        run_config_id: Annotated[
            str, Path(description="The unique identifier of the run configuration.")
        ],
        request: UpdateRunConfigRequest,
    ) -> TaskRunConfig:
        run_config = task_run_config_from_id(project_id, task_id, run_config_id)
        if run_config.path is None:
            raise HTTPException(
                status_code=400,
                detail="Cannot update this run config.",
            )
        if request.name is not None:
            run_config.name = request.name
        if request.starred is not None:
            run_config.starred = request.starred
        if request.prompt_name is not None:
            if run_config.prompt is None:
                raise HTTPException(
                    status_code=400,
                    detail="Run config has no frozen prompt to rename.",
                )
            run_config.prompt = run_config.prompt.model_copy(
                update={"name": request.prompt_name}
            )
        run_config.save_to_file()
        return run_config

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_eval_config",
        summary="Create Eval Config",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_eval_config(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        request: CreateEvalConfigRequest,
    ) -> EvalConfig:
        if request.type in (EvalConfigType.g_eval, EvalConfigType.llm_as_judge):
            if not request.model_name or not request.provider:
                raise HTTPException(
                    status_code=400,
                    detail="model_name and provider are required for LLM-based eval types.",
                )

        eval = eval_from_id(project_id, task_id, eval_id)
        name = request.name or generate_memorable_name()

        try:
            eval_config = EvalConfig(
                name=name,
                config_type=request.type,
                properties=request.properties,
                model_name=request.model_name,
                model_provider=request.provider,
                provenance=request.provenance,
                parent=eval,
            )
        except ValidationError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid properties for eval config type '{request.type.value}'.",
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
            )
        validate_provenance_or_400(
            eval_config.provenance,
            eval_config.id,
            EvalConfig,
            eval.path,
        )

        # Trust-conferral gate: saving a code eval admits new code as
        # trusted-forever, so it requires code trust for this session.
        # (Defense-in-depth: the frontend pre-checks trust before calling.)
        if isinstance(eval_config.properties, CodeEvalProperties):
            project = project_from_id(project_id)
            if not has_add_code_trust(str(project.path)):
                raise HTTPException(
                    status_code=403,
                    detail="Project not trusted to add code evals. Grant code trust and retry.",
                )

        eval_config.save_to_file()
        return eval_config

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_llm_judge_config",
        summary="Create LLM Judge Eval Config",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_llm_judge_config(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        request: CreateLlmJudgeConfigRequest,
    ) -> EvalConfig:
        eval = eval_from_id(project_id, task_id, eval_id)
        name = request.name or generate_memorable_name()

        try:
            properties = materialize_llm_judge_properties(
                eval=eval,
                model_name=request.model_name,
                model_provider=request.provider,
                g_eval=request.g_eval,
                judge_prompt=request.judge_prompt,
                system_prompt=request.system_prompt,
            )
            properties.reference_keys = list(request.reference_keys)
            eval_config = EvalConfig(
                name=name,
                config_type=EvalConfigType.v2,
                properties=properties,
                parent=eval,
            )
        except (ValidationError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
            )
        eval_config.save_to_file()
        return eval_config

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/default_llm_judge_prompt",
        summary="Get Default LLM Judge Prompt",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_default_llm_judge_prompt(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
    ) -> DefaultLlmJudgePromptResponse:
        eval = eval_from_id(project_id, task_id, eval_id)
        return DefaultLlmJudgePromptResponse(
            judge_prompt=build_default_llm_judge_prompt(eval),
            system_prompt=DEFAULT_SYSTEM_PROMPT,
        )

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval",
        summary="Test V2 Eval Config",
        tags=["Evals"],
        openapi_extra=DENY_AGENT,
    )
    async def test_v2_eval(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        request: TestV2EvalRequest,
    ) -> TestV2EvalResponse:
        try:
            eval_obj = eval_from_id(project_id, task_id, eval_id)

            if request.llm_judge_builder_input is not None:
                builder = request.llm_judge_builder_input
                properties = materialize_llm_judge_properties(
                    eval=eval_obj,
                    model_name=builder.model_name,
                    model_provider=builder.provider,
                    g_eval=builder.g_eval,
                    judge_prompt=builder.judge_prompt,
                    system_prompt=builder.system_prompt,
                )
            elif request.properties is not None:
                properties = request.properties
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Either properties or llm_judge_builder_input must be provided.",
                )

            transient_config = EvalConfig(
                name="test_run",
                config_type=EvalConfigType.v2,
                properties=properties,
                parent=eval_obj,
            )
            adapter = v2_eval_adapter_from_config(transient_config)

            # Trust-conferral gate: executing not-yet-saved code in the test pane
            # requires code trust for this session. Saved code needs no gate.
            if isinstance(adapter, CodeEvalAdapter):
                project = project_from_id(project_id)
                if not has_add_code_trust(str(project.path)):
                    return TestV2EvalResponse(
                        skipped_reason=SkippedReason.code_eval_not_trusted.value,
                        skipped_detail="Project not trusted for code eval execution.",
                    )

            result = await adapter.evaluate(request.eval_input)

            score_range_errors: list[str] | None = None
            if result.skipped_reason is None and result.scores:
                problems = validate_scores_against_output_scores(
                    result.scores, eval_obj.output_scores
                )
                if problems:
                    score_range_errors = problems

            return TestV2EvalResponse(
                scores=result.scores,
                skipped_reason=result.skipped_reason.value
                if result.skipped_reason
                else None,
                skipped_detail=result.skipped_detail,
                score_range_errors=score_range_errors,
                intermediate_outputs=result.intermediate_outputs,
            )
        except (ValueError, NotImplementedError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    # JS SSE client (EventSource) doesn't work with POST requests, so we use GET, even though post would be better
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_comparison",
        summary="Run Run Config Comparison",
        tags=["Evals"],
        # SSE run endpoint for the UI only. Agents kick off evals via the
        # non-streaming background job API (POST /api/jobs/evals).
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def run_eval_config(
        request: Request,
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        eval_config_id: Annotated[
            str, Path(description="The unique identifier of the eval configuration.")
        ],
        run_config_ids: Annotated[
            list[str],
            Query(description="The list of run configuration IDs to evaluate."),
        ] = [],
        all_run_configs: Annotated[
            bool,
            Query(
                description="Whether to evaluate all run configurations for the task."
            ),
        ] = False,
    ) -> StreamingResponse:
        """Run a specific eval config against one or more run configs and stream progress via SSE. Executes model runs and scores them."""
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)

        # Load the list of run configs to use. Two options:
        run_configs: list[TaskRunConfig] = []
        if all_run_configs:
            # special case, we cannot directly load task.run_configs(), we need to also get all finetune run configs which live inside the finetune model
            run_configs = get_all_run_configs(project_id, task_id)
        else:
            if len(run_config_ids) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="No run config ids provided. At least one run config id is required.",
                )
            run_configs = [
                task_run_config_from_id(project_id, task_id, run_config_id)
                for run_config_id in run_config_ids
            ]

        eval_runner = EvalRunner(
            eval_configs=[eval_config],
            run_configs=run_configs,
            eval_run_type="task_run_eval",
            save_context=build_save_context(request),
        )

        return await run_eval_runner_with_status(eval_runner)

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/set_current_eval_config/{eval_config_id}",
        summary="Set Default Eval Config",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def set_default_eval_config(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        eval_config_id: Annotated[
            str,
            Path(
                description="The unique identifier of the eval configuration to set as default, or 'None' to clear the default."
            ),
        ],
    ) -> Eval:
        eval = eval_from_id(project_id, task_id, eval_id)

        if eval_config_id == "None":
            eval.current_config_id = None
        else:
            eval_config = next(
                (
                    eval_config
                    for eval_config in eval.configs()
                    if eval_config.id == eval_config_id
                ),
                None,
            )
            if eval_config is None:
                raise HTTPException(
                    status_code=400,
                    detail="Eval config not found.",
                )
            eval.current_config_id = eval_config_id
        eval.save_to_file()

        return eval

    # JS SSE client (EventSource) doesn't work with POST requests, so we use GET, even though post would be better
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/run_calibration",
        summary="Run Calibration",
        tags=["Evals"],
        # SSE run endpoint for the UI only. Agents kick off evals via the
        # non-streaming background job API (POST /api/jobs/evals).
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def run_eval_config_eval(
        request: Request,
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
    ) -> StreamingResponse:
        """Run all eval configs against each other for calibration and stream progress via SSE. Used to check that eval configs produce consistent scores."""
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_configs = eval.configs()
        eval_runner = EvalRunner(
            eval_configs=eval_configs,
            run_configs=None,
            eval_run_type="eval_config_eval",
            save_context=build_save_context(request),
        )

        return await run_eval_runner_with_status(eval_runner)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results",
        summary="Get Eval Run Results",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval_run_results(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        eval_config_id: Annotated[
            str, Path(description="The unique identifier of the eval configuration.")
        ],
        run_config_id: Annotated[
            str, Path(description="The unique identifier of the run configuration.")
        ],
        split: Annotated[
            EvalSplitName | None,
            Query(
                description="Only return results for dataset items in this split of "
                "the eval (train, val, or test). 422 if the eval has no filter "
                "configured for the split. Omit to return all results (no split "
                "filtering)."
            ),
        ] = None,
    ) -> EvalRunResult:
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
        run_config = task_run_config_from_id(project_id, task_id, run_config_id)
        results = [
            run_result
            for run_result in eval_config.runs(readonly=True)
            if run_result.task_run_config_id == run_config_id
        ]
        if split is not None:
            task = task_from_id(project_id, task_id)
            # Resolved against the store this eval's items live in, so the
            # filter means the same thing here as it does in the summaries. A
            # V2 eval keys its runs on eval_input_id, and matching those
            # against TaskRun ids silently returned nothing at all.
            split_item_ids = split_item_ids_for_eval(task, eval, split, readonly=True)
            if split_item_ids is None:
                # A 422 rather than an empty list: this endpoint is asked for
                # one eval's runs, so a split it does not have is a bad
                # request. The task-wide summaries make the opposite call -
                # there, one eval without the split must not fail the page.
                #
                # An unset filter keeps split_filter_id_from_eval's wording, so
                # the two paths a caller can hit read the same; what reaches
                # the second branch is a filter that IS set and does not
                # resolve, which is a V2 eval carrying a TaskRun-only filter id.
                if eval.filter_id_for_split(split) is None:
                    field_name = (
                        "eval_set_filter_id"
                        if split == "test"
                        else f"{split}_set_filter_id"
                    )
                    raise HTTPException(
                        status_code=422,
                        detail=f"Eval '{eval.id}' has no {split} split configured "
                        f"(no {field_name}).",
                    )
                raise HTTPException(
                    status_code=422,
                    detail=f"Eval '{eval.id}' has a {split} split filter that does "
                    "not resolve against its own dataset "
                    f"({'EvalInputs' if eval_uses_eval_inputs(eval) else 'TaskRuns'}).",
                )
            results = [
                run_result
                for run_result in results
                if eval_run_item_id(run_result) in split_item_ids
            ]
        return EvalRunResult(
            results=results,
            eval=eval,
            eval_config=eval_config,
            run_config=run_config,
        )

    # Overview of the eval progress
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/progress",
        summary="Get Eval Progress",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval_progress(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
    ) -> EvalProgress:
        task = task_from_id(project_id, task_id)
        eval = eval_from_id(project_id, task_id, eval_id)
        # The eval slice is either TaskRun-typed (eval_set_filter_id) or
        # EvalInput-typed (eval_input_filter_id) — size the right source.
        expected_item_ids = expected_item_ids_for_eval(task, eval, readonly=True)
        if expected_item_ids is None:
            raise HTTPException(
                status_code=400,
                detail="This eval has no eval set filter (dataset or eval input source), so it has no items to score.",
            )
        dataset_size = len(expected_item_ids)
        golden_dataset_runs = (
            runs_in_filter(task, eval.eval_configs_filter_id, readonly=True)
            if eval.eval_configs_filter_id
            else []
        )

        # Count how many dataset items have human evals
        fully_rated_count, partially_rated_count, not_rated_count = count_human_evals(
            golden_dataset_runs,
            eval,
            build_score_key_to_task_requirement_id(task),
        )

        train_dataset_runs = (
            runs_in_filter(task, eval.train_set_filter_id, readonly=True)
            if eval.train_set_filter_id
            else []
        )

        current_eval_method = next(
            (
                eval_config
                for eval_config in eval.configs()
                if eval_config.id == eval.current_config_id
            ),
            None,
        )

        return EvalProgress(
            dataset_size=dataset_size,
            golden_dataset_size=len(golden_dataset_runs),
            golden_dataset_not_rated_count=not_rated_count,
            golden_dataset_partially_rated_count=partially_rated_count,
            golden_dataset_fully_rated_count=fully_rated_count,
            train_dataset_size=len(train_dataset_runs),
            current_eval_method=current_eval_method,
        )

    # This compares run_configs to each other on a given eval_config. Compare to below which compares eval_configs to each other.
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/score_summary",
        summary="Get Run Config Score Summary",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval_config_score_summary(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        eval_config_id: Annotated[
            str, Path(description="The unique identifier of the eval configuration.")
        ],
    ) -> EvalResultSummary:
        task = task_from_id(project_id, task_id)
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
        task_run_configs = get_all_run_configs(project_id, task_id)

        expected_item_ids = expected_item_ids_for_eval(task, eval, readonly=True)
        if expected_item_ids is None:
            raise HTTPException(
                status_code=400,
                detail="This eval has no eval set filter (dataset or eval input source), so it has no items to score.",
            )
        if len(expected_item_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="No items match this eval's eval set filter. Add items matching the filter to run this eval.",
            )

        return compute_score_summary(
            eval, eval_config, task_run_configs, expected_item_ids
        )

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/eval_results_summary",
        summary="Get Eval Results Summary",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval_results_summary(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        split: Annotated[
            EvalSplitQuery | None,
            Query(
                description="Scope the results to one dataset split: 'train', "
                "'val', 'test', or 'all' (every run that exists, plus the "
                "eval's own set as the denominator). Omit for each eval's own "
                "set, which is what 'test' means. Never fails on an eval that "
                "has no such split: that eval reports split_available=false "
                "and contributes no cells."
            ),
        ] = None,
    ) -> EvalResultsSummaryResponse:
        task = task_from_id(project_id, task_id)
        task_run_configs = get_all_run_configs(project_id, task_id)

        run_configs_out: Dict[ID_TYPE, EvalResultsSummaryRunConfigInfo] = {
            rc.id: EvalResultsSummaryRunConfigInfo(name=rc.name)
            for rc in task_run_configs
        }

        resolver = SplitItemResolver(task)
        evals_out: Dict[ID_TYPE, EvalResultsSummaryEvalInfo] = {}
        scores_out: Dict[ID_TYPE, Dict[ID_TYPE, EvalResultsSummaryResultCell]] = {}
        specs_by_eval = specs_by_eval_id(task)

        for eval in task.evals(readonly=True):
            if eval.eval_set_filter_id is None and eval.eval_input_filter_id is None:
                continue

            # Archived specs leave the comparison entirely, which is what
            # run_configs/{id}/eval_scores already does. Reporting an eval here
            # that endpoint drops left an archived eval's row on the page with a
            # mean but no sample size and no usage behind it.
            spec = specs_by_eval.get(eval.id)
            if spec is not None and spec.status == SpecStatus.archived:
                continue

            # "all" needs the judge config to know what has been run, so the
            # config is resolved before the item set rather than after.
            default_config = None
            if eval.current_config_id is not None:
                for eval_config in eval.configs(readonly=True):
                    if eval_config.id == eval.current_config_id:
                        default_config = eval_config
                        break

            expected_item_ids = resolver.items_for_query(eval, default_config, split)

            evals_out[eval.id] = EvalResultsSummaryEvalInfo(
                name=eval.name,
                default_judge_config_id=eval.current_config_id,
                dataset_size=len(expected_item_ids or []),
                output_score_keys=[s.json_key() for s in eval.output_scores],
                declared_splits=resolver.declared_splits(eval),
                split_available=expected_item_ids is not None,
            )

            if default_config is None or not expected_item_ids:
                continue

            summary = compute_score_summary(
                eval,
                default_config,
                task_run_configs,
                expected_item_ids,
            )

            for rc_id, scores_dict in summary.results.items():
                mean_scores = {
                    key: s.mean_score
                    for key, s in scores_dict.items()
                    if s.mean_score is not None
                }
                percent_complete = summary.run_config_percent_complete.get(rc_id, 0.0)
                cell = EvalResultsSummaryResultCell(
                    mean_scores=mean_scores,
                    percent_complete=percent_complete,
                    n_used_by_score_key={
                        key: s.n_used for key, s in scores_dict.items()
                    },
                )
                if rc_id not in scores_out:
                    scores_out[rc_id] = {}
                scores_out[rc_id][eval.id] = cell

        return EvalResultsSummaryResponse(
            evals_by_id=evals_out,
            run_configs_by_id=run_configs_out,
            scores_by_run_config_by_eval=scores_out,
            split=split,
        )

    # Compared to above, this is comparing all eval configs to each other, not looking at a single eval config
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_configs_score_summary",
        summary="Get Eval Config Comparison Summary",
        tags=["Evals"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_eval_configs_score_summary(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
    ) -> EvalConfigCompareSummary:
        task = task_from_id(project_id, task_id)
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_configs = eval.configs(readonly=True)

        score_key_to_task_requirement_id = build_score_key_to_task_requirement_id(task)

        # Build a set of all the dataset items IDs we expect to have scores for
        # Fetch all the dataset items in a filter, and return a map of dataset_id -> TaskRun
        if eval.eval_configs_filter_id is None:
            raise HTTPException(
                status_code=400,
                detail="No eval configs filter id set, cannot get eval configs score summary.",
            )

        filter = dataset_filter_from_id(eval.eval_configs_filter_id)
        expected_dataset_items = {run.id: run for run in task.runs() if filter(run)}
        expected_dataset_ids = set(expected_dataset_items.keys())
        if len(expected_dataset_ids) == 0:
            return EvalConfigCompareSummary(
                results={},
                eval_config_percent_complete={},
                dataset_size=0,
                fully_rated_count=0,
                partially_rated_count=0,
                not_rated_count=0,
            )

        # save a copy of the expected dataset ids for each eval config id, we'll update each as we process each eval run
        remaining_expected_dataset_ids: Dict[ID_TYPE, Set[ID_TYPE]] = {
            eval_config.id: set(expected_dataset_ids) for eval_config in eval_configs
        }

        # eval_config_id -> output_score_json_key -> correlation calculator
        correlation_calculators: Dict[ID_TYPE, Dict[str, CorrelationCalculator]] = {}

        for eval_config in eval_configs:
            for eval_run in eval_config.runs(readonly=True):
                dataset_item = expected_dataset_items.get(eval_run.dataset_id, None)
                if dataset_item is None:
                    # A dataset_id can be removed from the dataset filter (ran previously, then removed the tag to remove it from the eval config set filter)
                    # A dataset_id could be for an run_config, not for comparing eval at all
                    continue

                # Check if we should count this eval_run. Not every eval_run has to go into the stats:
                # Example: this dataset_id was already counted (not great there are dupes, but shouldn't be double counted if there are)
                if (
                    eval_run.dataset_id
                    not in remaining_expected_dataset_ids[eval_config.id]
                ):
                    continue
                else:
                    remaining_expected_dataset_ids[eval_config.id].remove(
                        eval_run.dataset_id
                    )

                for output_score in eval.output_scores:
                    # Custom scores are unbounded metrics with no normalization
                    # (normalize_rating raises on them), so correlation against
                    # human ratings is undefined — skip them.
                    if output_score.type == TaskOutputRatingType.custom:
                        continue

                    score_key = output_score.json_key()
                    eval_score: float | None = eval_run.scores.get(score_key, None)

                    # Fetch the human eval score from the dataset item
                    human_score = human_score_from_task_run(
                        dataset_item, output_score, score_key_to_task_requirement_id
                    )

                    if human_score is None or eval_score is None:
                        # This score doesn't have both a human eval and eval score, so we can't compare
                        continue

                    if eval_config.id not in correlation_calculators:
                        correlation_calculators[eval_config.id] = {}

                    calculator = correlation_calculators[eval_config.id].get(
                        score_key, None
                    )
                    if calculator is None:
                        calculator = CorrelationCalculator()
                        correlation_calculators[eval_config.id][score_key] = calculator

                    normalized_eval_score = normalize_rating(
                        eval_score, output_score.type
                    )
                    normalized_human_score = normalize_rating(
                        human_score, output_score.type
                    )
                    calculator.add_score(
                        CorrelationScore(
                            measured_score=eval_score,
                            human_score=human_score,
                            normalized_measured_score=normalized_eval_score,
                            normalized_human_score=normalized_human_score,
                        )
                    )

        # Convert to score summaries
        results: Dict[ID_TYPE, Dict[str, CorrelationResult]] = {}
        for eval_config_id in correlation_calculators.keys():
            results[eval_config_id] = {}
            for score_key in correlation_calculators[eval_config_id].keys():
                calculator = correlation_calculators[eval_config_id].get(
                    score_key, None
                )
                if calculator is None:
                    # No scores to calculate correlation for this pair
                    continue

                correlation_result = calculator.calculate_correlation()
                results[eval_config_id][score_key] = correlation_result

        # Calculate the percent of the dataset that has been processed
        eval_config_percent_complete: Dict[ID_TYPE, float] = {}
        for eval_config in eval_configs:
            incomplete_count = len(remaining_expected_dataset_ids[eval_config.id])
            percent_incomplete = incomplete_count / len(expected_dataset_ids)
            eval_config_percent_complete[eval_config.id] = 1 - percent_incomplete

        # Count how many dataset items have human evals
        fully_rated_count, partially_rated_count, not_rated_count = count_human_evals(
            list(expected_dataset_items.values()),
            eval,
            score_key_to_task_requirement_id,
        )

        return EvalConfigCompareSummary(
            results=results,
            eval_config_percent_complete=eval_config_percent_complete,
            dataset_size=len(expected_dataset_ids),
            fully_rated_count=fully_rated_count,
            partially_rated_count=partially_rated_count,
            not_rated_count=not_rated_count,
        )

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_scores",
        summary="Get Run Config Eval Scores",
        tags=["Run Configs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_run_config_eval_scores(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        run_config_id: Annotated[
            str, Path(description="The unique identifier of the run configuration.")
        ],
        split: Annotated[
            EvalSplitQuery | None,
            Query(
                description="Scope the scores and the usage averages to one "
                "dataset split: 'train', 'val', 'test', or 'all' (every run "
                "that exists). Omit for each eval's own set, which is what "
                "'test' means. An eval with no such split reports "
                "split_available=false rather than failing the request."
            ),
        ] = None,
    ) -> RunConfigEvalScoresSummary:
        task = task_from_id(project_id, task_id)

        # Verify the run config exists
        task_run_config_from_id(project_id, task_id, run_config_id)
        resolver = SplitItemResolver(task)

        # The spec behind each eval: its id labels the result, and an archived
        # one excludes the eval entirely (same rule as eval_results_summary).
        specs_by_eval = specs_by_eval_id(task)

        evals = task.evals()
        eval_results: List[RunConfigEvalResult] = []

        # Usage tracking across all eval configs for this run config
        total_input_tokens = 0.0
        total_output_tokens = 0.0
        total_total_tokens = 0.0
        total_cost = 0.0
        total_llm_latency_ms_sum = 0.0
        input_tokens_count = 0
        output_tokens_count = 0
        total_tokens_count = 0
        cost_count = 0
        latency_ms_count = 0
        total_eval_runs = 0

        for eval in evals:
            # Skip evals associated with archived specs
            spec = specs_by_eval.get(eval.id)
            if spec is not None and spec.status == SpecStatus.archived:
                continue

            declared_splits = resolver.declared_splits(eval)

            # Only process the default eval config (only if only one eval config, or default is set explicitly if many)
            # Resolved before the item set, which "all" reads runs out of.
            default_eval_config = None
            eval_configs = eval.configs(readonly=True)
            if len(eval_configs) == 1:
                default_eval_config = eval_configs[0]
            else:
                if eval.current_config_id:
                    default_eval_config = next(
                        (
                            config
                            for config in eval_configs
                            if config.id == eval.current_config_id
                        ),
                        None,
                    )

            # The items this eval is scored over, for the requested split
            expected_item_ids = resolver.items_for_query(
                eval, default_eval_config, split
            )
            if expected_item_ids is None:
                # No such split on this eval. Reported rather than dropped: a
                # missing eval reads as an eval that failed, and the page has
                # to be able to say "this one has no train set" instead.
                if (
                    eval.eval_set_filter_id is None
                    and eval.eval_input_filter_id is None
                ):
                    continue
                eval_results.append(
                    RunConfigEvalResult(
                        eval_id=eval.id,
                        eval_name=eval.name,
                        dataset_size=0,
                        eval_config_result=None,
                        missing_default_eval_config=default_eval_config is None,
                        spec_id=spec.id if spec is not None else None,
                        declared_splits=declared_splits,
                        split_available=False,
                    )
                )
                continue
            dataset_size = len(expected_item_ids)

            if not default_eval_config:
                # No default eval config set, so we can't process this eval. Still return it so UI can show an error
                eval_results.append(
                    RunConfigEvalResult(
                        eval_id=eval.id,
                        eval_name=eval.name,
                        dataset_size=dataset_size,
                        eval_config_result=None,
                        missing_default_eval_config=True,
                        spec_id=spec.id if spec is not None else None,
                        declared_splits=declared_splits,
                    )
                )
                continue

            eval_config = default_eval_config
            # Track which eval items we've seen for this eval_config
            remaining_expected_item_ids = set(expected_item_ids)
            partial_incomplete_count = 0
            eval_config_n_excluded = 0

            # output_score_json_key -> the individual scores, for the mean and
            # the percentile summary (see score_summary_from_values)
            score_values: Dict[str, list[float]] = {}

            for eval_run in eval_config.runs(readonly=True):
                # Only include eval_runs for our specific run_config
                if eval_run.task_run_config_id != run_config_id:
                    continue

                # Check if this eval run's item is expected for this eval
                item_id = eval_run_item_id(eval_run)
                if item_id not in remaining_expected_item_ids:
                    continue
                else:
                    remaining_expected_item_ids.remove(item_id)

                if eval_run.skipped_reason is not None:
                    eval_config_n_excluded += 1
                    continue

                total_eval_runs += 1

                # Get usage data from the corresponding TaskRun
                if eval_run.task_run_usage:
                    usage = eval_run.task_run_usage
                    if usage.input_tokens is not None:
                        total_input_tokens += usage.input_tokens
                        input_tokens_count += 1
                    if usage.output_tokens is not None:
                        total_output_tokens += usage.output_tokens
                        output_tokens_count += 1
                    if usage.total_tokens is not None:
                        total_total_tokens += usage.total_tokens
                        total_tokens_count += 1
                    if usage.cost is not None:
                        total_cost += usage.cost
                        cost_count += 1
                    if usage.total_llm_latency_ms is not None:
                        total_llm_latency_ms_sum += usage.total_llm_latency_ms
                        latency_ms_count += 1

                incomplete = False
                for output_score in eval.output_scores:
                    score_key = output_score.json_key()
                    if score_key not in score_values:
                        score_values[score_key] = []

                    if score_key in eval_run.scores:
                        score_values[score_key].append(eval_run.scores[score_key])
                    else:
                        # We're missing a required score, so this eval_run is incomplete
                        incomplete = True

                if incomplete:
                    partial_incomplete_count += 1

            results: Dict[str, ScoreSummary | None] = {}
            for output_score in eval.output_scores:
                score_key = output_score.json_key()
                values = score_values.get(score_key, [])
                if len(values) > 0 or eval_config_n_excluded > 0:
                    results[score_key] = score_summary_from_values(
                        values, eval_config_n_excluded
                    )
                else:
                    results[score_key] = None

            # Calculate the percent of the dataset that has been processed
            incomplete_count = partial_incomplete_count + len(
                remaining_expected_item_ids
            )
            if dataset_size > 0:
                percent_incomplete = incomplete_count / dataset_size
                percent_complete = 1 - percent_incomplete
            else:
                percent_complete = 0.0

            eval_results.append(
                RunConfigEvalResult(
                    eval_id=eval.id,
                    eval_name=eval.name,
                    dataset_size=dataset_size,
                    missing_default_eval_config=False,
                    spec_id=spec.id if spec is not None else None,
                    eval_config_result=EvalConfigResult(
                        eval_config_id=eval_config.id,
                        results=results,
                        percent_complete=percent_complete,
                        n_excluded=eval_config_n_excluded,
                    ),
                    declared_splits=declared_splits,
                )
            )

        # Calculate mean usage across all eval runs for this run config (only include values where >= 50% of samples have data)
        mean_usage = None
        if total_eval_runs > 0:
            threshold = total_eval_runs * 0.5
            mean_usage = MeanUsage(
                mean_input_tokens=total_input_tokens / input_tokens_count
                if input_tokens_count >= threshold
                else None,
                mean_output_tokens=total_output_tokens / output_tokens_count
                if output_tokens_count >= threshold
                else None,
                mean_total_tokens=total_total_tokens / total_tokens_count
                if total_tokens_count >= threshold
                else None,
                mean_cost=total_cost / cost_count if cost_count >= threshold else None,
                mean_total_llm_latency_ms=total_llm_latency_ms_sum / latency_ms_count
                if latency_ms_count >= threshold
                else None,
            )

        return RunConfigEvalScoresSummary(
            eval_results=eval_results,
            mean_usage=mean_usage,
            split=split,
            n_eval_runs=total_eval_runs,
        )

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_run_index",
        summary="Get Run Config Eval Run Index",
        tags=["Run Configs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_run_config_eval_run_index(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        run_config_id: Annotated[
            str, Path(description="The unique identifier of the run configuration.")
        ],
        split: Annotated[
            EvalSplitQuery | None,
            Query(
                description="Scope the rows to one dataset split: 'train', "
                "'val', 'test', or 'all' (every run that exists). Omit for each "
                "eval's own set, which is what 'test' means. An eval with no "
                "such split contributes no entry."
            ),
        ] = None,
    ) -> EvalRunIndexResponse:
        """Every eval run this run config has, one row each, without the traces.

        The aggregating siblings (eval_results_summary, eval_scores) answer
        "what did this config score", which is all a page needs while every
        config is measured on whatever runs happen to exist. Comparing configs
        on the SAME conversations needs the rows themselves - which items each
        config covered, and how big each conversation was - and there is no way
        to intersect item sets from a mean.

        Scoped exactly like eval_scores, so a number computed from these rows
        can only differ from the aggregate one by the filtering the caller
        applied: the eval's current default judge config only, archived-spec
        evals skipped, the split resolved through SplitItemResolver, skipped
        runs excluded, and at most one row per item (first wins, in
        eval_config.runs() order - the same rule and the same iteration order
        compute_score_summary dedupes with, so both surfaces pick the same run
        when a job race left two).
        """
        task = task_from_id(project_id, task_id)

        # Verify the run config exists
        task_run_config_from_id(project_id, task_id, run_config_id)
        resolver = SplitItemResolver(task)

        specs_by_eval = specs_by_eval_id(task)

        index_evals: List[EvalRunIndexEval] = []

        for eval in task.evals():
            # Skip evals associated with archived specs
            spec = specs_by_eval.get(eval.id)
            if spec is not None and spec.status == SpecStatus.archived:
                continue

            # Only the default eval config (only if only one eval config, or
            # default is set explicitly if many). Resolved before the item set,
            # which "all" reads runs out of.
            default_eval_config = None
            eval_configs = eval.configs(readonly=True)
            if len(eval_configs) == 1:
                default_eval_config = eval_configs[0]
            elif eval.current_config_id:
                default_eval_config = next(
                    (
                        config
                        for config in eval_configs
                        if config.id == eval.current_config_id
                    ),
                    None,
                )
            if default_eval_config is None:
                continue

            expected_item_ids = resolver.items_for_query(
                eval, default_eval_config, split
            )
            if expected_item_ids is None:
                continue

            remaining_expected_item_ids = set(expected_item_ids)
            rows: List[EvalRunIndexRow] = []

            for eval_run in default_eval_config.runs(readonly=True):
                if eval_run.task_run_config_id != run_config_id:
                    continue

                item_id = eval_run_item_id(eval_run)
                if item_id not in remaining_expected_item_ids:
                    continue
                # The item's slot is consumed HERE, before the skip test, so a
                # skipped run and a scored one for the same item leave exactly
                # one row - the first in iteration order - and a skipped first
                # takes the item off the index entirely. That is deliberate,
                # and it is deliberate because compute_score_summary does the
                # same thing at the same point (:1099-1110): these rows exist
                # to be intersected with numbers that endpoint produced, so a
                # different dedupe here would make a matched mean and an
                # unfiltered mean disagree about a config nobody filtered out.
                # No behavior change - stated so the next reader does not
                # "fix" it into a divergence.
                remaining_expected_item_ids.remove(item_id)

                if eval_run.skipped_reason is not None:
                    continue

                usage = eval_run.task_run_usage
                rows.append(
                    EvalRunIndexRow(
                        item_id=item_id,
                        eval_run_id=eval_run.id,
                        execution_id=eval_run_execution_id(eval_run),
                        scores=dict(eval_run.scores),
                        input_tokens=usage.input_tokens if usage else None,
                        output_tokens=usage.output_tokens if usage else None,
                        total_tokens=usage.total_tokens if usage else None,
                        cost=usage.cost if usage else None,
                        total_llm_latency_ms=usage.total_llm_latency_ms
                        if usage
                        else None,
                    )
                )

            index_evals.append(
                EvalRunIndexEval(
                    eval_id=eval.id,
                    eval_config_id=default_eval_config.id,
                    rows=rows,
                )
            )

        return EvalRunIndexResponse(evals=index_evals, split=split)

    @app.post(
        "/api/projects/{project_id}/add_code_trust",
        summary="Add code trust for a project",
        tags=["Evals"],
        openapi_extra=DENY_AGENT,
    )
    async def add_code_trust_endpoint(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> CodeTrustResponse:
        project = project_from_id(project_id)
        add_code_trust(str(project.path))
        return CodeTrustResponse(trusted=True)

    @app.get(
        "/api/projects/{project_id}/add_code_trust",
        summary="Check code trust for a project",
        tags=["Evals"],
        openapi_extra=DENY_AGENT,
    )
    async def check_add_code_trust_endpoint(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> CodeTrustResponse:
        project = project_from_id(project_id)
        return CodeTrustResponse(trusted=has_add_code_trust(str(project.path)))
