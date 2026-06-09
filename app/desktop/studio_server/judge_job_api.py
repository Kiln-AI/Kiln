from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query, Request
from kiln_ai.adapters.eval.judge_job_runner import (
    DEFAULT_FAILURE_THRESHOLD,
    JudgeJobItemError,
    JudgeJobRunner,
)
from kiln_ai.datamodel.eval import EvalConfig, EvalDataType
from kiln_ai.datamodel.judge_job import JudgeJob, JudgeJobRun
from kiln_ai.datamodel.task import Task
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.git_sync_decorators import build_save_context, no_write_lock
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, Field, model_validator


def judge_job_from_id(project_id: str, task_id: str, judge_job_id: str) -> JudgeJob:
    task = task_from_id(project_id, task_id)
    judge_job = JudgeJob.from_id_and_parent_path(judge_job_id, task.path)
    if judge_job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Judge job not found. ID: {judge_job_id}",
        )
    return judge_job


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


class CreateJudgeJobRequest(BaseModel):
    """Request to create a judge job."""

    name: str | None = Field(
        default=None,
        description="The name of the judge job. A memorable name is generated if omitted.",
    )
    description: str | None = Field(
        default=None, description="A description of the judge job."
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
    def validate_request(self) -> "CreateJudgeJobRequest":
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


class JudgeJobRunResponse(BaseModel):
    """The result of running a judge job. Counts and errors are FYI for the caller; not persisted."""

    judge_job: JudgeJob = Field(description="The judge job that was run.")
    failing_runs: list[JudgeJobRun] = Field(
        description="The failing examples found (up to stop_after_failures, if set), with feedback."
    )
    judged_runs: list[JudgeJobRun] = Field(
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
    errors: list[JudgeJobItemError] = Field(
        default_factory=list,
        description="Per-item judge/save errors (if any). Each is skipped, not retried; re-running "
        "the job retries the un-persisted items. A non-empty list means partial success.",
    )


def _build_judge_job(task: Task, request: CreateJudgeJobRequest) -> JudgeJob:
    return JudgeJob(
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


async def _run_judge_job(
    judge_job: JudgeJob, eval_config: EvalConfig, request: Request
) -> JudgeJobRunResponse:
    runner = JudgeJobRunner(
        judge_job, eval_config, save_context=build_save_context(request)
    )
    result = await runner.run()
    return JudgeJobRunResponse(
        judge_job=judge_job,
        failing_runs=result.failing_runs,
        judged_runs=result.judged_runs,
        num_judged=result.num_judged,
        failing_count=result.failing_count,
        train_set_size=result.train_set_size,
        hit_cap=result.hit_cap,
        errors=result.errors,
    )


def connect_judge_job_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/judge_jobs",
        summary="Create Judge Job",
        tags=["Judge Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_judge_job(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        request: CreateJudgeJobRequest,
    ) -> JudgeJob:
        """Create a judge job config. Run it later with `/judge_jobs/{id}/run`."""
        task = task_from_id(project_id, task_id)
        # Validate the judge (eval config) and optional run config exist under this task.
        eval_config = eval_config_from_id(task, request.eval_config_id)
        validate_judge_eval(eval_config, request.generate_outputs)
        validate_run_config_id(task, request.run_config_id)
        judge_job = _build_judge_job(task, request)
        judge_job.save_to_file()
        return judge_job

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/judge_jobs/{judge_job_id}/run",
        summary="Run Judge Job",
        tags=["Judge Jobs"],
        openapi_extra=agent_policy_require_approval(
            "Run judge job? It makes model calls over the sampled dataset items."
        ),
    )
    @no_write_lock
    async def run_judge_job(
        request: Request,
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        judge_job_id: Annotated[
            str, Path(description="The unique identifier of the judge job.")
        ],
    ) -> JudgeJobRunResponse:
        """Run a judge job: sample tagged dataset items, judge their existing outputs, and return
        the failing examples + feedback.

        Runs synchronously and returns once judging completes. Each result is persisted as a child
        run (fetch them later via `GET /judge_jobs/{id}/runs`); the returned counts
        (num_judged, failing_count, train_set_size, hit_cap) and any per-item `errors` are FYI for
        the caller's loop. Errors don't abort the run — partial results are still persisted, and
        re-running the job retries only the un-persisted (errored or not-yet-judged) items.
        """
        task = task_from_id(project_id, task_id)
        judge_job = judge_job_from_id(project_id, task_id, judge_job_id)
        eval_config = eval_config_from_id(task, judge_job.eval_config_id)
        validate_judge_eval(eval_config, judge_job.generate_outputs)
        return await _run_judge_job(judge_job, eval_config, request)

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/judge_jobs/run",
        summary="Create And Run Judge Job",
        tags=["Judge Jobs"],
        openapi_extra=agent_policy_require_approval(
            "Create and run judge job? It makes model calls over the sampled dataset items."
        ),
    )
    @no_write_lock
    async def create_and_run_judge_job(
        request: Request,
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        body: CreateJudgeJobRequest,
    ) -> JudgeJobRunResponse:
        """Create a judge job and run it immediately (synchronous), returning the failing examples
        + feedback."""
        task = task_from_id(project_id, task_id)
        eval_config = eval_config_from_id(task, body.eval_config_id)
        validate_judge_eval(eval_config, body.generate_outputs)
        validate_run_config_id(task, body.run_config_id)
        judge_job = _build_judge_job(task, body)
        judge_job.save_to_file()
        return await _run_judge_job(judge_job, eval_config, request)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/judge_jobs",
        summary="List Judge Jobs",
        tags=["Judge Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_judge_jobs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> list[JudgeJob]:
        """List all judge jobs for a task."""
        return task_from_id(project_id, task_id).judge_jobs()

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/judge_jobs/{judge_job_id}",
        summary="Get Judge Job",
        tags=["Judge Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_judge_job(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        judge_job_id: Annotated[
            str, Path(description="The unique identifier of the judge job.")
        ],
    ) -> JudgeJob:
        """Get a judge job config."""
        return judge_job_from_id(project_id, task_id, judge_job_id)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/judge_jobs/{judge_job_id}/runs",
        summary="Get Judge Job Runs",
        tags=["Judge Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_judge_job_runs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        judge_job_id: Annotated[
            str, Path(description="The unique identifier of the judge job.")
        ],
        failing_only: Annotated[
            bool,
            Query(description="Return only the items that failed the judge."),
        ] = False,
    ) -> list[JudgeJobRun]:
        """Get the per-item judge results (task_run_id, scores, feedback, passed) for a judge job."""
        judge_job = judge_job_from_id(project_id, task_id, judge_job_id)
        runs = judge_job.runs()
        if failing_only:
            runs = [run for run in runs if not run.passed]
        return runs
