import json
from collections import defaultdict
from typing import Annotated, Any, Dict, List, Set, Tuple

from fastapi import FastAPI, HTTPException, Path, Query, Request
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
from kiln_ai.datamodel.dataset_filters import DatasetFilterId, dataset_filter_from_id
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalOutputScore,
    EvalRun,
    EvalTemplateId,
)
from kiln_ai.datamodel.json_schema import string_to_json_key
from kiln_ai.datamodel.prompt_id import is_frozen_prompt
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.spec import SpecStatus
from kiln_ai.datamodel.task import RunConfigProperties, TaskRunConfig
from kiln_ai.datamodel.task_output import normalize_rating
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.git_sync_decorators import build_save_context, no_write_lock
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


def eval_from_id(project_id: str, task_id: str, eval_id: str) -> Eval:
    task = task_from_id(project_id, task_id)
    eval = Eval.from_id_and_parent_path(eval_id, task.path)
    if eval is not None:
        return eval

    raise HTTPException(
        status_code=404,
        detail=f"Eval not found. ID: {eval_id}",
    )


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
    model_name: str = Field(description="The model to use for evaluation.")
    provider: ModelProviderName = Field(
        description="The provider of the evaluation model."
    )


class CreateTaskRunConfigRequest(BaseModel):
    """Request to create a new run config for eval."""

    name: str | None = Field(default=None, description="The name of the run config.")
    description: str | None = Field(
        default=None, description="The description of the run config."
    )
    run_config_properties: RunConfigProperties = Field(
        description="The run configuration properties."
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

    mean_score: float = Field(description="The mean score across all runs.")


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
    dataset_size: int = Field(description="Total size of the eval dataset.")
    output_score_keys: list[str] = Field(
        description="The output score keys for this eval."
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


class RunConfigEvalResult(BaseModel):
    """Eval results for a specific run config."""

    eval_id: ID_TYPE = Field(description="The unique identifier of the eval.")
    eval_name: str = Field(description="The human-readable name of the eval.")
    dataset_size: int = Field(description="The dataset size for this eval.")
    eval_config_result: EvalConfigResult | None = Field(
        default=None, description="The eval config results, if available."
    )
    missing_default_eval_config: bool = Field(
        description="Whether the default eval config is missing."
    )
    spec_id: ID_TYPE | None = Field(
        default=None, description="The associated spec ID, if any."
    )


class RunConfigEvalScoresSummary(BaseModel):
    """Summary of all eval scores for a run config."""

    eval_results: List[RunConfigEvalResult] = Field(
        description="Eval results for each eval."
    )
    mean_usage: MeanUsage | None = Field(
        default=None, description="Average usage statistics across eval runs."
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

    # Task requirement ratings
    req_id = score_key_to_task_requirement_id.get(score_key, None)
    if req_id:
        req_rating = task_run.output.rating.requirement_ratings.get(req_id, None)
        if req_rating is not None:
            return req_rating.value
        return None

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


def compute_score_summary(
    eval: Eval,
    eval_config: EvalConfig,
    task_run_configs: list[TaskRunConfig],
    expected_dataset_ids: set[ID_TYPE],
) -> EvalResultSummary:
    if len(expected_dataset_ids) == 0:
        return EvalResultSummary(
            results={},
            run_config_percent_complete={},
            dataset_size=0,
        )

    remaining_expected_dataset_ids: Dict[ID_TYPE, Set[ID_TYPE]] = {
        run_config.id: set(expected_dataset_ids) for run_config in task_run_configs
    }
    partial_incomplete_counts: Dict[ID_TYPE, int] = {
        run_config.id: 0 for run_config in task_run_configs
    }

    total_scores: Dict[ID_TYPE, Dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    score_counts: Dict[ID_TYPE, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for eval_run in eval_config.runs(readonly=True):
        if eval_run.task_run_config_id is None:
            continue
        run_config_id = eval_run.task_run_config_id

        if run_config_id not in remaining_expected_dataset_ids:
            continue
        if eval_run.dataset_id not in remaining_expected_dataset_ids[run_config_id]:
            continue
        else:
            remaining_expected_dataset_ids[run_config_id].remove(eval_run.dataset_id)

        incomplete = False
        # Ensure this run_config_id has an entry even if no scores match
        _ = total_scores[run_config_id]
        for output_score in eval.output_scores:
            score_key = output_score.json_key()
            if score_key in eval_run.scores:
                total_scores[run_config_id][score_key] += eval_run.scores[score_key]
                score_counts[run_config_id][score_key] += 1
            else:
                incomplete = True

        if incomplete:
            partial_incomplete_counts[run_config_id] += 1

    results: Dict[ID_TYPE, Dict[str, ScoreSummary]] = {}
    for run_config_id, output_scores in total_scores.items():
        results[run_config_id] = {}
        for output_score_id, score in output_scores.items():
            count = score_counts[run_config_id][output_score_id]
            if count > 0:
                results[run_config_id][output_score_id] = ScoreSummary(
                    mean_score=score / count
                )

    run_config_percent_complete: Dict[ID_TYPE, float] = {}
    for run_config in task_run_configs:
        incomplete_count = partial_incomplete_counts[run_config.id] + len(
            remaining_expected_dataset_ids[run_config.id]
        )
        percent_incomplete = incomplete_count / len(expected_dataset_ids)
        run_config_percent_complete[run_config.id] = 1 - percent_incomplete

    return EvalResultSummary(
        results=results,
        run_config_percent_complete=run_config_percent_complete,
        dataset_size=len(expected_dataset_ids),
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
        run_config_properties = request.run_config_properties
        if isinstance(run_config_properties, KilnAgentRunConfigProperties):
            prompt_id = run_config_properties.prompt_id
            if not is_frozen_prompt(prompt_id):
                # For dynamic prompts, we "freeze" a copy of this prompt into the task run config so we don't accidentally invalidate evals if the user changes something that impacts the prompt (example: changing data for multi-shot, or changing task for basic-prompt)
                # We then point the task_run_config.run_properties.prompt_id to this new frozen prompt
                prompt_builder = prompt_builder_from_id(prompt_id, task)
                prompt_name = generate_memorable_name()
                frozen_prompt = BasePrompt(
                    name=prompt_name,
                    description=f"Frozen copy of prompt '{prompt_id}'.",
                    generator_id=prompt_id,
                    prompt=prompt_builder.build_base_prompt(),
                    chain_of_thought_instructions=prompt_builder.chain_of_thought_prompt(),
                )
        task_run_config = TaskRunConfig(
            parent=task,
            name=name,
            run_config_properties=run_config_properties,
            description=request.description,
            prompt=frozen_prompt,
        )
        if frozen_prompt is not None:
            # Set after, because the ID isn't known until the TaskRunConfig is created
            if isinstance(
                task_run_config.run_config_properties, KilnAgentRunConfigProperties
            ):
                task_run_config.run_config_properties.prompt_id = f"task_run_config::{parent_project.id}::{task.id}::{task_run_config.id}"
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
        eval = eval_from_id(project_id, task_id, eval_id)
        name = request.name or generate_memorable_name()

        eval_config = EvalConfig(
            name=name,
            config_type=request.type,
            properties=request.properties,
            model_name=request.model_name,
            model_provider=request.provider,
            parent=eval,
        )
        eval_config.save_to_file()
        return eval_config

    # JS SSE client (EventSource) doesn't work with POST requests, so we use GET, even though post would be better
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_comparison",
        summary="Run Run Config Comparison",
        tags=["Evals"],
        openapi_extra=agent_policy_require_approval("Run eval comparison?"),
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
            # special case, we cannot directly lod task.run_configs(), we need to also get all finetune run configs which lives inside the finetune model
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
        openapi_extra=agent_policy_require_approval(
            "Run eval calibration? This runs LLM calls across all eval configs and uses AI credits."
        ),
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
    ) -> EvalRunResult:
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
        run_config = task_run_config_from_id(project_id, task_id, run_config_id)
        results = [
            run_result
            for run_result in eval_config.runs(readonly=True)
            if run_result.task_run_config_id == run_config_id
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
        dataset_ids = dataset_ids_in_filter(
            task, eval.eval_set_filter_id, readonly=True
        )
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
            dataset_size=len(dataset_ids),
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

        expected_dataset_ids = dataset_ids_in_filter(
            task, eval.eval_set_filter_id, readonly=True
        )
        if len(expected_dataset_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="No dataset ids in eval set filter. Add items to your dataset matching the eval set filter.",
            )

        return compute_score_summary(
            eval, eval_config, task_run_configs, expected_dataset_ids
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
    ) -> EvalResultsSummaryResponse:
        task = task_from_id(project_id, task_id)
        task_run_configs = get_all_run_configs(project_id, task_id)

        run_configs_out: Dict[ID_TYPE, EvalResultsSummaryRunConfigInfo] = {
            rc.id: EvalResultsSummaryRunConfigInfo(name=rc.name)
            for rc in task_run_configs
        }

        dataset_ids_cache: Dict[DatasetFilterId, Set[ID_TYPE]] = {}
        evals_out: Dict[ID_TYPE, EvalResultsSummaryEvalInfo] = {}
        scores_out: Dict[ID_TYPE, Dict[ID_TYPE, EvalResultsSummaryResultCell]] = {}

        for eval in task.evals(readonly=True):
            filter_id = eval.eval_set_filter_id
            if filter_id not in dataset_ids_cache:
                dataset_ids_cache[filter_id] = dataset_ids_in_filter(
                    task, filter_id, readonly=True
                )
            expected_dataset_ids = dataset_ids_cache[filter_id]

            evals_out[eval.id] = EvalResultsSummaryEvalInfo(
                name=eval.name,
                default_judge_config_id=eval.current_config_id,
                dataset_size=len(expected_dataset_ids),
                output_score_keys=[s.json_key() for s in eval.output_scores],
            )

            if eval.current_config_id is None:
                continue

            default_config = None
            for eval_config in eval.configs(readonly=True):
                if eval_config.id == eval.current_config_id:
                    default_config = eval_config
                    break

            if default_config is None or len(expected_dataset_ids) == 0:
                continue

            summary = compute_score_summary(
                eval,
                default_config,
                task_run_configs,
                expected_dataset_ids,
            )

            for rc_id, scores_dict in summary.results.items():
                mean_scores = {key: s.mean_score for key, s in scores_dict.items()}
                percent_complete = summary.run_config_percent_complete.get(rc_id, 0.0)
                cell = EvalResultsSummaryResultCell(
                    mean_scores=mean_scores,
                    percent_complete=percent_complete,
                )
                if rc_id not in scores_out:
                    scores_out[rc_id] = {}
                scores_out[rc_id][eval.id] = cell

        return EvalResultsSummaryResponse(
            evals_by_id=evals_out,
            run_configs_by_id=run_configs_out,
            scores_by_run_config_by_eval=scores_out,
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
    ) -> RunConfigEvalScoresSummary:
        task = task_from_id(project_id, task_id)

        # Verify the run config exists
        task_run_config_from_id(project_id, task_id, run_config_id)

        # Build a mapping from eval_id to spec_id for evals that are associated with specs
        # Also track which eval_ids belong to archived specs so we can exclude them
        specs = task.specs()
        eval_id_to_spec_id: Dict[str, str] = {}
        archived_eval_ids: set[str] = set()
        for spec in specs:
            if spec.eval_id and spec.id:
                eval_id_to_spec_id[spec.eval_id] = spec.id
                if spec.status == SpecStatus.archived:
                    archived_eval_ids.add(spec.eval_id)

        evals = task.evals()
        eval_results: List[RunConfigEvalResult] = []

        # Usage tracking across all eval configs for this run config
        total_input_tokens = 0.0
        total_output_tokens = 0.0
        total_total_tokens = 0.0
        total_cost = 0.0
        input_tokens_count = 0
        output_tokens_count = 0
        total_tokens_count = 0
        cost_count = 0
        total_eval_runs = 0

        for eval in evals:
            # Skip evals associated with archived specs
            if eval.id and eval.id in archived_eval_ids:
                continue

            # Get the dataset size for this eval
            expected_dataset_ids = dataset_ids_in_filter(
                task, eval.eval_set_filter_id, readonly=True
            )
            dataset_size = len(expected_dataset_ids)

            # Only process the default eval config (only if only one eval config, or default is set explicitly if many)
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

            if not default_eval_config:
                # No default eval config set, so we can't process this eval. Still return it so UI can show an error
                eval_results.append(
                    RunConfigEvalResult(
                        eval_id=eval.id,
                        eval_name=eval.name,
                        dataset_size=dataset_size,
                        eval_config_result=None,
                        missing_default_eval_config=True,
                        spec_id=eval_id_to_spec_id.get(eval.id) if eval.id else None,
                    )
                )
                continue

            eval_config = default_eval_config
            # Track which dataset items we've seen for this eval_config
            remaining_expected_dataset_ids = set(expected_dataset_ids)
            partial_incomplete_count = 0

            # output_score_json_key -> score/total for calculating the mean score
            total_scores: Dict[str, float] = {}
            score_counts: Dict[str, int] = {}

            for eval_run in eval_config.runs(readonly=True):
                # Only include eval_runs for our specific run_config
                if eval_run.task_run_config_id != run_config_id:
                    continue

                # Check if this dataset_id is expected for this eval
                if eval_run.dataset_id not in remaining_expected_dataset_ids:
                    continue
                else:
                    remaining_expected_dataset_ids.remove(eval_run.dataset_id)

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

                incomplete = False
                for output_score in eval.output_scores:
                    score_key = output_score.json_key()
                    if score_key not in total_scores:
                        total_scores[score_key] = 0
                        score_counts[score_key] = 0

                    if score_key in eval_run.scores:
                        total_scores[score_key] += eval_run.scores[score_key]
                        score_counts[score_key] += 1
                    else:
                        # We're missing a required score, so this eval_run is incomplete
                        incomplete = True

                if incomplete:
                    partial_incomplete_count += 1

            # Initialize results with all expected score keys as None
            results: Dict[str, ScoreSummary | None] = {}
            for output_score in eval.output_scores:
                score_key = output_score.json_key()
                results[score_key] = None

            # Convert to score summaries where we have data
            for output_score_id, score in total_scores.items():
                count = score_counts[output_score_id]
                if count > 0:
                    results[output_score_id] = ScoreSummary(mean_score=score / count)

            # Calculate the percent of the dataset that has been processed
            incomplete_count = partial_incomplete_count + len(
                remaining_expected_dataset_ids
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
                    spec_id=eval_id_to_spec_id.get(eval.id) if eval.id else None,
                    eval_config_result=EvalConfigResult(
                        eval_config_id=eval_config.id,
                        results=results,
                        percent_complete=percent_complete,
                    ),
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
            )

        return RunConfigEvalScoresSummary(
            eval_results=eval_results,
            mean_usage=mean_usage,
        )
