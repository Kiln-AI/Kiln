import json
import re
from typing import Any, Dict, List, Set, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from kiln_ai.adapters.eval.eval_runner import EvalRunner
from kiln_ai.adapters.ml_model_list import ModelProviderName, built_in_models
from kiln_ai.adapters.prompt_builders import prompt_builder_from_id
from kiln_ai.datamodel import (
    BasePrompt,
    DataSource,
    DataSourceType,
    Task,
    TaskRun,
)
from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    MAX_SHORT_NAME_LENGTH,
    NAME_REGEX,
    string_to_valid_name,
)
from kiln_ai.datamodel.dataset_filters import DatasetFilterId, dataset_filter_from_id
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalRun,
    EvalTemplateId,
)
from kiln_ai.datamodel.json_schema import string_to_json_key
from kiln_ai.datamodel.prompt_id import PromptGenerators, is_frozen_prompt
from kiln_ai.datamodel.task import RunConfigProperties, TaskRunConfig
from kiln_ai.datamodel.task_output import normalize_rating
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.task_api import task_from_id
from pydantic import BaseModel

from .correlation_calculator import (
    CorrelationCalculator,
    CorrelationResult,
    CorrelationScore,
)


def eval_from_id(project_id: str, task_id: str, eval_id: str) -> Eval:
    task = task_from_id(project_id, task_id)
    for eval in task.evals():
        if eval.id == eval_id:
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


def task_run_config_from_id(
    project_id: str, task_id: str, run_config_id: str
) -> TaskRunConfig:
    task = task_from_id(project_id, task_id)
    for run_config in task.run_configs():
        if run_config.id == run_config_id:
            return run_config

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

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
    )


class CreateEvaluatorRequest(BaseModel):
    name: str
    description: str
    template: EvalTemplateId | None
    output_scores: list[EvalOutputScore]
    eval_set_filter_id: DatasetFilterId
    eval_configs_filter_id: DatasetFilterId


class CreateEvalConfigRequest(BaseModel):
    name: str | None = None
    type: EvalConfigType
    properties: dict[str, Any]
    model_name: str
    provider: ModelProviderName


class CreateTaskRunConfigRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    run_config_properties: RunConfigProperties


class RunEvalConfigRequest(BaseModel):
    run_config_ids: list[str]


class ScoreSummary(BaseModel):
    mean_score: float


class EvalRunResult(BaseModel):
    results: List[EvalRun]
    eval: Eval
    eval_config: EvalConfig
    run_config: TaskRunConfig


class UpdateFavouriteRequest(BaseModel):
    favourite: bool


class EvalProgress(BaseModel):
    # The total size of the dataset used for the eval
    dataset_size: int
    # The total size of the golden dataset used for the eval
    golden_dataset_size: int
    # The number of golden dataset items, by rating progress
    golden_dataset_not_rated_count: int
    golden_dataset_partially_rated_count: int
    golden_dataset_fully_rated_count: int
    # The current selected eval method
    current_eval_method: EvalConfig | None
    # The current selected run method
    current_run_method: TaskRunConfig | None


class EvalResultSummary(BaseModel):
    # run_config_id -> output_score_id -> ScoreSummary
    results: Dict[ID_TYPE, Dict[str, ScoreSummary]]
    # run_config_id -> percent of the dataset that has been processed
    run_config_percent_complete: Dict[ID_TYPE, float]
    # The total size of the dataset used for the eval
    dataset_size: int


class EvalConfigCompareSummary(BaseModel):
    # Summary of results. eval_config_id -> output_score_id -> CorrelationResult
    results: Dict[ID_TYPE, Dict[str, CorrelationResult]]
    # eval_config_id -> percent of the dataset that has been processed (run with eval scores)
    eval_config_percent_complete: Dict[ID_TYPE, float]
    # The total size of the dataset used for the eval config comparisons (eval.eval_configs_filter_id set size)
    dataset_size: int
    # The number of dataset items which are fully rated, partially rated, or not rated at all.
    fully_rated_count: int
    partially_rated_count: int
    not_rated_count: int


class UpdateEvalRequest(BaseModel):
    name: str
    description: str | None = None


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


def connect_evals_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/create_evaluator")
    async def create_evaluator(
        project_id: str,
        task_id: str,
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
            parent=task,
        )
        eval.save_to_file()
        return eval

    @app.get("/api/projects/{project_id}/tasks/{task_id}/task_run_configs")
    async def get_task_run_configs(
        project_id: str, task_id: str
    ) -> list[TaskRunConfig]:
        task = task_from_id(project_id, task_id)
        return task.run_configs()

    @app.get("/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}")
    async def get_eval(project_id: str, task_id: str, eval_id: str) -> Eval:
        return eval_from_id(project_id, task_id, eval_id)

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}")
    async def update_eval(
        project_id: str, task_id: str, eval_id: str, request: UpdateEvalRequest
    ) -> Eval:
        eval = eval_from_id(project_id, task_id, eval_id)
        eval.name = request.name
        eval.description = request.description
        eval.save_to_file()
        return eval

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/fav")
    async def update_eval_favourite(
        project_id: str, task_id: str, eval_id: str, request: UpdateFavouriteRequest
    ) -> Eval:
        eval = eval_from_id(project_id, task_id, eval_id)
        eval.favourite = request.favourite
        eval.save_to_file()
        return eval

    @app.delete("/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}")
    async def delete_eval(project_id: str, task_id: str, eval_id: str) -> None:
        eval = eval_from_id(project_id, task_id, eval_id)
        eval.delete()

    @app.get("/api/projects/{project_id}/tasks/{task_id}/evals")
    async def get_evals(project_id: str, task_id: str) -> list[Eval]:
        task = task_from_id(project_id, task_id)
        return task.evals()

    @app.get("/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_configs")
    async def get_eval_configs(
        project_id: str, task_id: str, eval_id: str
    ) -> list[EvalConfig]:
        eval = eval_from_id(project_id, task_id, eval_id)
        return eval.configs()

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}"
    )
    async def get_eval_config(
        project_id: str, task_id: str, eval_id: str, eval_config_id: str
    ) -> EvalConfig:
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
        return eval_config

    @app.post("/api/projects/{project_id}/tasks/{task_id}/task_run_config")
    async def create_task_run_config(
        project_id: str,
        task_id: str,
        request: CreateTaskRunConfigRequest,
    ) -> TaskRunConfig:
        task = task_from_id(project_id, task_id)
        name = request.name or generate_task_run_config_name(
            request.run_config_properties.model_name,
            request.run_config_properties.prompt_id,
            task,
        )

        parent_project = task.parent_project()
        if parent_project is None:
            raise HTTPException(
                status_code=400,
                detail="Task must have a parent project.",
            )

        frozen_prompt: BasePrompt | None = None
        prompt_id = request.run_config_properties.prompt_id
        if not is_frozen_prompt(prompt_id):
            # For dynamic prompts, we "freeze" a copy of this prompt into the task run config so we don't accidentially invalidate evals if the user changes something that impacts the prompt (example: chanding data for multi-shot, or chanding task for basic-prompt)
            # We then point the task_run_config.run_properties.prompt_id to this new frozen prompt
            prompt_builder = prompt_builder_from_id(prompt_id, task)
            prompt_name = generate_memorable_name()
            frozen_prompt = BasePrompt(
                name=prompt_name,
                description=f"Frozen copy of prompt '{prompt_id}', created for evaluations.",
                generator_id=prompt_id,
                prompt=prompt_builder.build_base_prompt(),
                chain_of_thought_instructions=prompt_builder.chain_of_thought_prompt(),
            )

        run_config_properties = request.run_config_properties

        task_run_config = TaskRunConfig(
            parent=task,
            name=name,
            run_config_properties=run_config_properties,
            description=request.description,
            prompt=frozen_prompt,
        )
        if frozen_prompt is not None:
            # Set after, because the ID isn't known until the TaskRunConfig is created
            task_run_config.run_config_properties.prompt_id = (
                f"task_run_config::{parent_project.id}::{task.id}::{task_run_config.id}"
            )
        task_run_config.save_to_file()
        return task_run_config

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/create_eval_config"
    )
    async def create_eval_config(
        project_id: str,
        task_id: str,
        eval_id: str,
        request: CreateEvalConfigRequest,
    ) -> EvalConfig:
        eval = eval_from_id(project_id, task_id, eval_id)
        name = request.name or generate_eval_config_name(
            request.type, request.model_name
        )

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
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}/run_task_run_eval"
    )
    async def run_eval_config(
        project_id: str,
        task_id: str,
        eval_id: str,
        eval_config_id: str,
        run_config_ids: list[str] = Query([]),
        all_run_configs: bool = Query(False),
    ) -> StreamingResponse:
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)

        # Load the list of run configs to use. Two options:
        run_configs: list[TaskRunConfig] = []
        if all_run_configs:
            run_configs = task_from_id(project_id, task_id).run_configs()
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
        )

        return await run_eval_runner_with_status(eval_runner)

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/set_current_eval_config/{eval_config_id}"
    )
    async def set_default_eval_config(
        project_id: str,
        task_id: str,
        eval_id: str,
        eval_config_id: str | None,
    ) -> Eval:
        eval = eval_from_id(project_id, task_id, eval_id)

        if eval_config_id == "None":
            eval_config_id = None
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

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/set_current_run_config/{run_config_id}"
    )
    async def set_default_run_config(
        project_id: str,
        task_id: str,
        eval_id: str,
        run_config_id: str | None,
    ) -> Eval:
        task = task_from_id(project_id, task_id)

        # Confirm the run config exists, unless the user is clearing the default run config
        if run_config_id == "None":
            run_config_id = None
        else:
            run_config = next(
                (
                    run_config
                    for run_config in task.run_configs()
                    if run_config.id == run_config_id
                ),
                None,
            )
            if run_config is None:
                raise HTTPException(
                    status_code=400,
                    detail="Run config not found.",
                )

        eval = eval_from_id(project_id, task_id, eval_id)
        eval.current_run_config_id = run_config_id
        eval.save_to_file()

        return eval

    # JS SSE client (EventSource) doesn't work with POST requests, so we use GET, even though post would be better
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/run_eval_config_eval"
    )
    async def run_eval_config_eval(
        project_id: str,
        task_id: str,
        eval_id: str,
    ) -> StreamingResponse:
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_configs = eval.configs()
        eval_runner = EvalRunner(
            eval_configs=eval_configs,
            run_configs=None,
            eval_run_type="eval_config_eval",
        )

        return await run_eval_runner_with_status(eval_runner)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results"
    )
    async def get_eval_run_results(
        project_id: str,
        task_id: str,
        eval_id: str,
        eval_config_id: str,
        run_config_id: str,
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
    @app.get("/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/progress")
    async def get_eval_progress(
        project_id: str,
        task_id: str,
        eval_id: str,
    ) -> EvalProgress:
        task = task_from_id(project_id, task_id)
        eval = eval_from_id(project_id, task_id, eval_id)
        dataset_ids = dataset_ids_in_filter(
            task, eval.eval_set_filter_id, readonly=True
        )
        golden_dataset_runs = runs_in_filter(
            task, eval.eval_configs_filter_id, readonly=True
        )

        # Count how many dataset items have human evals
        fully_rated_count, partially_rated_count, not_rated_count = count_human_evals(
            golden_dataset_runs,
            eval,
            build_score_key_to_task_requirement_id(task),
        )

        current_eval_method = next(
            (
                eval_config
                for eval_config in eval.configs()
                if eval_config.id == eval.current_config_id
            ),
            None,
        )

        current_run_method = next(
            (
                run_config
                for run_config in task.run_configs()
                if run_config.id == eval.current_run_config_id
            ),
            None,
        )

        return EvalProgress(
            dataset_size=len(dataset_ids),
            golden_dataset_size=len(golden_dataset_runs),
            golden_dataset_not_rated_count=not_rated_count,
            golden_dataset_partially_rated_count=partially_rated_count,
            golden_dataset_fully_rated_count=fully_rated_count,
            current_eval_method=current_eval_method,
            current_run_method=current_run_method,
        )

    # This compares run_configs to each other on a given eval_config. Compare to below which compares eval_configs to each other.
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}/score_summary"
    )
    async def get_eval_config_score_summary(
        project_id: str,
        task_id: str,
        eval_id: str,
        eval_config_id: str,
    ) -> EvalResultSummary:
        task = task_from_id(project_id, task_id)
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
        task_runs_configs = task.run_configs()

        # Build a set of all the dataset items IDs we expect to have scores for
        expected_dataset_ids = dataset_ids_in_filter(
            task, eval.eval_set_filter_id, readonly=True
        )
        if len(expected_dataset_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="No dataset ids in eval set filter. Add items to your dataset matching the eval set filter.",
            )

        # save a copy of the expected dataset ids for each run config, we'll update each as we process each eval run
        remaining_expected_dataset_ids: Dict[ID_TYPE, Set[ID_TYPE]] = {
            run_config.id: set(expected_dataset_ids) for run_config in task_runs_configs
        }
        # Track how often we are missing scores in a eval_config. Should be 0 for a complete eval_config
        partial_incomplete_counts: Dict[ID_TYPE, int] = {
            run_config.id: 0 for run_config in task_runs_configs
        }

        # task_run_config_id -> output_score_json_key -> score/total for calculating the mean score
        total_scores: Dict[ID_TYPE, Dict[str, float]] = {}
        score_counts: Dict[ID_TYPE, Dict[str, int]] = {}

        for eval_run in eval_config.runs(readonly=True):
            if eval_run.task_run_config_id is None:
                # This eval_run is not associated with a run_config, so we should not count it
                continue
            run_config_id = eval_run.task_run_config_id

            # Check if we should count this eval_run. Not every eval_run has to go into the stats:
            # - a dataset_id can be removed from the dataset filter (removed a tag)
            # - this dataset_id was already counted (not great there are dupes, but shouldn't be double counted if there are)
            if run_config_id not in remaining_expected_dataset_ids:
                # This run_config is not in the eval config, so we should not count it
                continue
            if eval_run.dataset_id not in remaining_expected_dataset_ids[run_config_id]:
                continue
            else:
                remaining_expected_dataset_ids[run_config_id].remove(
                    eval_run.dataset_id
                )

            incomplete = False
            for output_score in eval.output_scores:
                score_key = output_score.json_key()
                if run_config_id not in total_scores:
                    total_scores[run_config_id] = {}
                    score_counts[run_config_id] = {}
                if score_key not in total_scores[run_config_id]:
                    total_scores[run_config_id][score_key] = 0
                    score_counts[run_config_id][score_key] = 0
                if score_key in eval_run.scores:
                    total_scores[run_config_id][score_key] += eval_run.scores[score_key]
                    score_counts[run_config_id][score_key] += 1
                else:
                    # We're missing a required score, so this eval_run is incomplete
                    incomplete = True

            if incomplete:
                partial_incomplete_counts[run_config_id] += 1

        # Convert to score summaries
        results: Dict[ID_TYPE, Dict[str, ScoreSummary]] = {}
        for run_config_id, output_scores in total_scores.items():
            results[run_config_id] = {}
            for output_score_id, score in output_scores.items():
                count = score_counts[run_config_id][output_score_id]
                if count > 0:
                    results[run_config_id][output_score_id] = ScoreSummary(
                        mean_score=score / count
                    )

        # Calculate the percent of the dataset that has been processed
        run_config_percent_complete: Dict[ID_TYPE, float] = {}
        for run_config in task_runs_configs:
            # Partial incomplete (missing scores), and fully incomplete (no eval_run)
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

    # Compared to above, this is comparing all eval configs to each other, not looking at a single eval config
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_configs_score_summary"
    )
    async def get_eval_configs_score_summary(
        project_id: str,
        task_id: str,
        eval_id: str,
    ) -> EvalConfigCompareSummary:
        task = task_from_id(project_id, task_id)
        eval = eval_from_id(project_id, task_id, eval_id)
        eval_configs = eval.configs(readonly=True)

        score_key_to_task_requirement_id = build_score_key_to_task_requirement_id(task)

        # Build a set of all the dataset items IDs we expect to have scores for
        # Fetch all the dataset items in a filter, and return a map of dataset_id -> TaskRun
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


def generate_task_run_config_name(model_id: str, prompt_id: str, task: Task) -> str:
    """Generate a descriptive name for a task run config in format: {model_name} - {prompt_name}

    Args:
        model_id: The model ID from the run config (e.g. "gpt-4o", "claude-3-5-sonnet")
        prompt_id: The prompt ID from the run config properties
        task: The task to use for prompt name resolution

    Returns:
        str: A descriptive name following NAME_REGEX and within MAX_SHORT_NAME_LENGTH
    """
    # Get human-readable model name
    model_name = _get_model_display_name(model_id)

    # Get prompt name
    prompt_name = _get_prompt_display_name(prompt_id, task)

    # Create base name
    base_name = f"{model_name} - {prompt_name}"

    # Ensure it follows NAME_REGEX and length constraints
    return _sanitize_name(base_name)


def generate_eval_config_name(eval_type: EvalConfigType, model_id: str) -> str:
    """Generate a descriptive name for an eval config in format: {eval_method} - {model_name}

    Args:
        eval_type: The type of evaluation (g_eval, llm_as_judge)
        model_id: The model ID from the eval config (e.g. "gpt-4o", "claude-3-5-sonnet")

    Returns:
        str: A descriptive name following NAME_REGEX and within MAX_SHORT_NAME_LENGTH
    """
    # Get human-readable eval method name
    eval_method = _get_eval_method_display_name(eval_type)

    # Get human-readable model name
    model_name = _get_model_display_name(model_id)

    # Create base name
    base_name = f"{eval_method} - {model_name}"

    # Ensure it follows NAME_REGEX and length constraints
    return _sanitize_name(base_name)


_prompt_generator_names = {
    PromptGenerators.SIMPLE.value: "Basic Prompt",
    PromptGenerators.SHORT.value: "Short Prompt",
    PromptGenerators.FEW_SHOT.value: "Few Shot Prompt",
    PromptGenerators.MULTI_SHOT.value: "Multi Shot Prompt",
    PromptGenerators.REPAIRS.value: "Repairs Prompt",
    PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT.value: "Basic CoT Prompt",
    PromptGenerators.FEW_SHOT_CHAIN_OF_THOUGHT.value: "Few Shot CoT Prompt",
    PromptGenerators.MULTI_SHOT_CHAIN_OF_THOUGHT.value: "Multi Shot CoT Prompt",
}


def _get_prompt_display_name(prompt_id: str, task: Task) -> str:
    """Get a human-readable display name for a prompt ID"""
    # Handle saved prompts (id::prompt_id)
    if prompt_id.startswith("id::"):
        actual_prompt_id = prompt_id[4:]
        prompt_model = next(
            (p for p in task.prompts(readonly=True) if p.id == actual_prompt_id),
            None,
        )
        if prompt_model:
            return prompt_model.name
        return "Saved Prompt"

    # Handle fine-tune prompts (fine_tune_prompt::fine_tune_id)
    if prompt_id.startswith("fine_tune_prompt::"):
        return "Fine Tune Prompt"

    return _prompt_generator_names.get(prompt_id, "Unknown")


def _get_eval_method_display_name(eval_type: EvalConfigType) -> str:
    """Get a human-readable display name for an eval config type"""
    eval_method_names = {
        EvalConfigType.g_eval: "G-Eval",
        EvalConfigType.llm_as_judge: "LLM as Judge",
    }
    return eval_method_names.get(eval_type, "Unknown")


def _get_model_display_name(model_id: str) -> str:
    """Get a human-readable display name for a model ID"""
    # Search through all built-in models to find one with a matching model_id
    for model in built_in_models:
        if model.name == model_id:
            return model.friendly_name

    # If not found, return the model_id as-is (fallback)
    return model_id


def _sanitize_name(name: str) -> str:
    """Sanitize a name to follow NAME_REGEX and MAX_SHORT_NAME_LENGTH constraints"""
    # Use the existing string_to_valid_name function to handle regex compliance
    valid_name = string_to_valid_name(name)

    # Truncate if too long, preserving the most important parts
    if len(valid_name) > MAX_SHORT_NAME_LENGTH:
        valid_name = valid_name[:MAX_SHORT_NAME_LENGTH].rstrip()

    # Ensure we have at least one character
    if not valid_name:
        return generate_memorable_name()

    return valid_name
