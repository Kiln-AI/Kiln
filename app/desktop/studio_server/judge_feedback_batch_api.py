from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query, Request
from kiln_ai.adapters.eval.judge_feedback_batch_runner import (
    DEFAULT_FAILURE_THRESHOLD,
    JudgeFeedbackBatchItemError,
    JudgeFeedbackBatchRunner,
)
from kiln_ai.datamodel.eval import EvalConfig, EvalDataType
from kiln_ai.datamodel.judge_feedback_batch import (
    JudgeFeedbackBatch,
    JudgeFeedbackBatchRun,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.usage import Usage
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.git_sync_decorators import build_save_context, no_write_lock
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, Field, model_validator


def judge_feedback_batch_from_id(
    project_id: str, task_id: str, judge_feedback_batch_id: str
) -> JudgeFeedbackBatch:
    task = task_from_id(project_id, task_id)
    judge_feedback_batch = JudgeFeedbackBatch.from_id_and_parent_path(
        judge_feedback_batch_id, task.path
    )
    if judge_feedback_batch is None:
        raise HTTPException(
            status_code=404,
            detail=f"Judge job not found. ID: {judge_feedback_batch_id}",
        )
    return judge_feedback_batch


def eval_config_from_id(task: Task, eval_config_id: str) -> EvalConfig:
    """Resolve an eval config by ID across all of the task's evals (the judge)."""
    for eval in task.evals():
        for config in eval.configs():
            if config.id == eval_config_id:
                return config
    raise HTTPException(
        status_code=404,
        detail=f"Eval config not found. ID: {eval_config_id}",
    )


def validate_run_config_id(task: Task, run_config_id: str | None) -> None:
    """If a run_config_id is provided (metadata), confirm it is a real run config for the task."""
    if run_config_id and not any(rc.id == run_config_id for rc in task.run_configs()):
        raise HTTPException(
            status_code=404,
            detail=f"Run config not found. ID: {run_config_id}",
        )


def validate_judge_eval(eval_config: EvalConfig, generate_outputs: bool) -> None:
    """Reference-answer evals score a candidate output against the dataset's reference answer, which
    only makes sense when generating a fresh output. Judging an existing output gives nothing to
    compare against, so reject that combination (the judge would otherwise error on every item)."""
    eval = eval_config.parent_eval()
    if (
        eval is not None
        and eval.evaluation_data_type == EvalDataType.reference_answer
        and not generate_outputs
    ):
        raise HTTPException(
            status_code=422,
            detail="Reference-answer evals require generate_outputs=true; there is no reference to "
            "compare a pre-existing output against.",
        )


class CreateJudgeFeedbackBatchRequest(BaseModel):
    """Request to create a judge feedback batch."""

    name: str | None = Field(
        default=None,
        description="The name of the judge feedback batch. A memorable name is generated if omitted.",
    )
    description: str | None = Field(
        default=None, description="A description of the judge feedback batch."
    )
    target_tags: list[str] = Field(
        description="Dataset items must carry all of these tags to be sampled. At least one required.",
    )
    eval_config_id: str = Field(
        description="The ID of the eval config (the judge) used to score sampled items."
    )
    run_config_id: str | None = Field(
        default=None,
        description="The ID of the run config. Metadata when judging existing outputs; required and "
        "run on each item when generate_outputs=true.",
    )
    generate_outputs: bool = Field(
        default=False,
        description="If true, run run_config_id on each sampled item to generate a fresh output and "
        "judge that (gate a candidate, scoped to the tagged items). If false, judge existing outputs.",
    )
    stop_after_failures: int | None = Field(
        default=None,
        ge=1,
        description="If set, stop once this many failing examples are found (a cheap minibatch for "
        "the train signal). If null (default), judge the whole matching set up to max_samples (full "
        "coverage — required for a val gate paired by task_run_id).",
    )
    max_samples: int = Field(
        default=50,
        ge=1,
        description="The maximum number of items to judge.",
    )
    threshold: float = Field(
        default=DEFAULT_FAILURE_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="The normalized (0-1) pass bar. A score below this counts as failing.",
    )

    @model_validator(mode="after")
    def validate_request(self) -> "CreateJudgeFeedbackBatchRequest":
        if (
            self.stop_after_failures is not None
            and self.max_samples < self.stop_after_failures
        ):
            raise ValueError("max_samples must be >= stop_after_failures")
        if not self.target_tags or any(not t.strip() for t in self.target_tags):
            raise ValueError("target_tags must be a non-empty list of non-empty tags")
        if self.generate_outputs and not self.run_config_id:
            raise ValueError("run_config_id is required when generate_outputs is true")
        return self


class JudgeFeedbackBatchRunResponse(BaseModel):
    """The result of running a judge feedback batch. Counts and errors are FYI for the caller; not persisted."""

    judge_feedback_batch: JudgeFeedbackBatch = Field(
        description="The judge feedback batch that was run."
    )
    failing_runs: list[JudgeFeedbackBatchRun] = Field(
        description="The failing examples found (up to stop_after_failures, if set), with feedback."
    )
    judged_runs: list[JudgeFeedbackBatchRun] = Field(
        description="Every item judged this run (pass and fail), each keyed by task_run_id. Pair "
        "these across two runs by task_run_id to gate a candidate vs baseline on the same items.",
    )
    num_judged: int = Field(
        description="How many items were examined while searching for failures."
    )
    failing_count: int = Field(description="How many judged items failed the judge.")
    train_set_size: int = Field(
        description="Total number of dataset items matching the target tags."
    )
    hit_cap: bool = Field(
        description="True if coverage was capped: max_samples reached before stop_after_failures "
        "(train signal), or the matching set exceeded max_samples (gate).",
    )
    errors: list[JudgeFeedbackBatchItemError] = Field(
        default_factory=list,
        description="Per-item judge/save errors (if any). Each is skipped, not retried; re-running "
        "the job retries the un-persisted items. A non-empty list means partial success.",
    )
    mean_normalized_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Mean normalized (0-1, higher = better) score per output-score dimension over "
        "judged_runs — the continuous signal the pass/fail bit discards. Use it as a gate/loss "
        "metric (compare a candidate's mean vs the baseline's) instead of just the failure count.",
    )
    mean_normalized_score: float | None = Field(
        default=None,
        description="Mean of mean_normalized_scores across dimensions (null if nothing was judged).",
    )
    total_usage: Usage | None = Field(
        default=None,
        description="Summed token usage, cost (USD), and LLM latency for generating the judged "
        "outputs. Populated only in generate_outputs mode (null when existing outputs were judged). "
        "The deterministic counterpart to mean_normalized_scores — weigh quality against cost/latency "
        "(a Pareto axis), and accumulate cost/elapsed across calls for an advisory budget readout.",
    )
    mean_cost: float | None = Field(
        default=None,
        description="Mean generation cost (USD) per judged item, over the items that reported cost "
        "(null in judge-only mode). Per-item cost lives on each judged_runs[].usage.",
    )
    mean_latency_ms: float | None = Field(
        default=None,
        description="Mean generation LLM latency (ms) per judged item, over the items that reported "
        "latency (null in judge-only mode). Per-item latency lives on each judged_runs[].usage.",
    )


def _build_judge_feedback_batch(
    task: Task, request: CreateJudgeFeedbackBatchRequest
) -> JudgeFeedbackBatch:
    return JudgeFeedbackBatch(
        parent=task,
        name=request.name or generate_memorable_name(),
        description=request.description,
        target_tags=request.target_tags,
        eval_config_id=request.eval_config_id,
        run_config_id=request.run_config_id,
        generate_outputs=request.generate_outputs,
        stop_after_failures=request.stop_after_failures,
        max_samples=request.max_samples,
        threshold=request.threshold,
    )


async def _run_judge_feedback_batch(
    judge_feedback_batch: JudgeFeedbackBatch, eval_config: EvalConfig, request: Request
) -> JudgeFeedbackBatchRunResponse:
    runner = JudgeFeedbackBatchRunner(
        judge_feedback_batch, eval_config, save_context=build_save_context(request)
    )
    result = await runner.run()
    return JudgeFeedbackBatchRunResponse(
        judge_feedback_batch=judge_feedback_batch,
        failing_runs=result.failing_runs,
        judged_runs=result.judged_runs,
        num_judged=result.num_judged,
        failing_count=result.failing_count,
        train_set_size=result.train_set_size,
        hit_cap=result.hit_cap,
        errors=result.errors,
        mean_normalized_scores=result.mean_normalized_scores,
        mean_normalized_score=result.mean_normalized_score,
        total_usage=result.total_usage,
        mean_cost=result.mean_cost,
        mean_latency_ms=result.mean_latency_ms,
    )


def connect_judge_feedback_batch_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/judge_feedback_batches",
        summary="Create Judge Feedback Batch",
        tags=["Judge Feedback Batches"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_judge_feedback_batch(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        request: CreateJudgeFeedbackBatchRequest,
    ) -> JudgeFeedbackBatch:
        """Create a judge feedback batch config. Run it later with `/judge_feedback_batches/{id}/run`."""
        task = task_from_id(project_id, task_id)
        # Validate the judge (eval config) and optional run config exist under this task.
        eval_config = eval_config_from_id(task, request.eval_config_id)
        validate_judge_eval(eval_config, request.generate_outputs)
        validate_run_config_id(task, request.run_config_id)
        judge_feedback_batch = _build_judge_feedback_batch(task, request)
        judge_feedback_batch.save_to_file()
        return judge_feedback_batch

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/judge_feedback_batches/{judge_feedback_batch_id}/run",
        summary="Run Judge Feedback Batch",
        tags=["Judge Feedback Batches"],
        openapi_extra=agent_policy_require_approval(
            "Run judge feedback batch? It makes model calls over the sampled dataset items."
        ),
    )
    @no_write_lock
    async def run_judge_feedback_batch(
        request: Request,
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        judge_feedback_batch_id: Annotated[
            str, Path(description="The unique identifier of the judge feedback batch.")
        ],
    ) -> JudgeFeedbackBatchRunResponse:
        """Run a judge feedback batch: sample tagged dataset items, judge their existing outputs, and return
        the failing examples + feedback.

        Runs synchronously and returns once judging completes. Each result is persisted as a child
        run (fetch them later via `GET /judge_feedback_batches/{id}/runs`); the returned counts
        (num_judged, failing_count, train_set_size, hit_cap) and any per-item `errors` are FYI for
        the caller's loop. Errors don't abort the run — partial results are still persisted, and
        re-running the job retries only the un-persisted (errored or not-yet-judged) items.
        """
        task = task_from_id(project_id, task_id)
        judge_feedback_batch = judge_feedback_batch_from_id(
            project_id, task_id, judge_feedback_batch_id
        )
        eval_config = eval_config_from_id(task, judge_feedback_batch.eval_config_id)
        validate_judge_eval(eval_config, judge_feedback_batch.generate_outputs)
        return await _run_judge_feedback_batch(
            judge_feedback_batch, eval_config, request
        )

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/judge_feedback_batches/run",
        summary="Create And Run Judge Feedback Batch",
        tags=["Judge Feedback Batches"],
        openapi_extra=agent_policy_require_approval(
            "Create and run judge feedback batch? It makes model calls over the sampled dataset items."
        ),
    )
    @no_write_lock
    async def create_and_run_judge_feedback_batch(
        request: Request,
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        body: CreateJudgeFeedbackBatchRequest,
    ) -> JudgeFeedbackBatchRunResponse:
        """Create a judge feedback batch and run it immediately (synchronous), returning the failing examples
        + feedback."""
        task = task_from_id(project_id, task_id)
        eval_config = eval_config_from_id(task, body.eval_config_id)
        validate_judge_eval(eval_config, body.generate_outputs)
        validate_run_config_id(task, body.run_config_id)
        judge_feedback_batch = _build_judge_feedback_batch(task, body)
        judge_feedback_batch.save_to_file()
        return await _run_judge_feedback_batch(
            judge_feedback_batch, eval_config, request
        )

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/judge_feedback_batches",
        summary="List Judge Feedback Batches",
        tags=["Judge Feedback Batches"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_judge_feedback_batches(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> list[JudgeFeedbackBatch]:
        """List all judge feedback batches for a task."""
        return task_from_id(project_id, task_id).judge_feedback_batches()

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/judge_feedback_batches/{judge_feedback_batch_id}",
        summary="Get Judge Feedback Batch",
        tags=["Judge Feedback Batches"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_judge_feedback_batch(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        judge_feedback_batch_id: Annotated[
            str, Path(description="The unique identifier of the judge feedback batch.")
        ],
    ) -> JudgeFeedbackBatch:
        """Get a judge feedback batch config."""
        return judge_feedback_batch_from_id(
            project_id, task_id, judge_feedback_batch_id
        )

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/judge_feedback_batches/{judge_feedback_batch_id}/runs",
        summary="Get Judge Feedback Batch Runs",
        tags=["Judge Feedback Batches"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_judge_feedback_batch_runs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        judge_feedback_batch_id: Annotated[
            str, Path(description="The unique identifier of the judge feedback batch.")
        ],
        failing_only: Annotated[
            bool,
            Query(description="Return only the items that failed the judge."),
        ] = False,
    ) -> list[JudgeFeedbackBatchRun]:
        """Get the per-item judge results (task_run_id, scores, feedback, passed) for a judge feedback batch."""
        judge_feedback_batch = judge_feedback_batch_from_id(
            project_id, task_id, judge_feedback_batch_id
        )
        runs = judge_feedback_batch.runs()
        if failing_only:
            runs = [run for run in runs if not run.passed]
        return runs
