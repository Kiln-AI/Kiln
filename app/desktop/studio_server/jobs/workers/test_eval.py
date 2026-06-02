from __future__ import annotations

from contextlib import contextmanager
from typing import AsyncIterator
from unittest.mock import patch

import pytest
from app.desktop.studio_server.jobs.models import BackgroundJobStatus
from app.desktop.studio_server.jobs.registry import JobRegistry
from app.desktop.studio_server.jobs.workers.eval import (
    EvalJobParams,
    EvalJobResult,
    EvalJobWorker,
)
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalOutputScore,
    EvalRun,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode, TaskRunConfig
from kiln_ai.utils.async_job_runner import Progress


@pytest.fixture
def project(tmp_path):
    project = Project(
        id="project1", name="Test Project", path=tmp_path / "project.kiln"
    )
    project.save_to_file()
    return project


@pytest.fixture
def task(project):
    task = Task(
        id="task1",
        name="Test Task",
        description="test",
        instruction="do the thing",
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def eval(task):
    eval = Eval(
        id="eval1",
        name="Test Eval",
        description="test",
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id="tag::golden",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Check accuracy",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        parent=task,
    )
    eval.save_to_file()
    return eval


@pytest.fixture
def eval_config(eval):
    eval_config = EvalConfig(
        id="eval_config1",
        name="Test Eval Config",
        model_name="gpt-4",
        model_provider="openai",
        properties={"eval_steps": ["step1", "step2"]},
        parent=eval,
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def run_config(task):
    run_config = TaskRunConfig(
        id="run_config1",
        name="Test Run Config",
        description="test",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()
    return run_config


@pytest.fixture
def data_source():
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "gpt-4",
            "model_provider": "openai",
            "adapter_name": "test_adapter",
        },
    )


@pytest.fixture
def params():
    return EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="eval1",
        eval_config_id="eval_config1",
        run_config_id="run_config1",
    )


@pytest.fixture
def resolve_project(project):
    """Make the eval_api entity helpers resolve the on-disk project by id.

    task_from_id binds project_from_id into kiln_server.task_api, so we patch it
    there (the name as looked up), not at its definition site.
    """
    with patch("kiln_server.task_api.project_from_id", return_value=project):
        yield project


def _make_task_run(task, data_source, tag: str) -> TaskRun:
    task_run = TaskRun(
        parent=task,
        input="test",
        input_source=data_source,
        tags=[tag],
        output=TaskOutput(output="test"),
    )
    task_run.save_to_file()
    return task_run


def _make_eval_run(eval_config, dataset_id, run_config_id) -> EvalRun:
    eval_run = EvalRun(
        parent=eval_config,
        dataset_id=dataset_id,
        task_run_config_id=run_config_id,
        input="test",
        output="test",
        scores={"accuracy": 1.0},
    )
    eval_run.save_to_file()
    return eval_run


@contextmanager
def _stub_eval_runner_run(progresses: list[Progress]):
    async def fake_run(self, concurrency: int = 25) -> AsyncIterator[Progress]:
        for progress in progresses:
            yield progress

    with patch(
        "kiln_ai.adapters.eval.eval_runner.EvalRunner.run",
        new=fake_run,
    ):
        yield


# -- compute_state -----------------------------------------------------------


async def test_compute_state_no_eval_runs(
    resolve_project, task, eval_config, run_config, data_source, params
):
    for _ in range(3):
        _make_task_run(task, data_source, "eval_set")
    # A task run outside the eval-set filter must not be counted toward total.
    _make_task_run(task, data_source, "other")

    state = await EvalJobWorker().compute_state(params)

    assert state.total == 3
    assert state.success == 0
    assert state.error == 0
    assert state.is_complete is False


async def test_compute_state_counts_already_scored(
    resolve_project, task, eval_config, run_config, data_source, params
):
    task_runs = [_make_task_run(task, data_source, "eval_set") for _ in range(3)]
    _make_eval_run(eval_config, task_runs[0].id, run_config.id)
    _make_eval_run(eval_config, task_runs[1].id, run_config.id)

    state = await EvalJobWorker().compute_state(params)

    assert state.total == 3
    assert state.success == 2
    assert state.is_complete is False


async def test_compute_state_is_complete(
    resolve_project, task, eval_config, run_config, data_source, params
):
    task_runs = [_make_task_run(task, data_source, "eval_set") for _ in range(2)]
    for task_run in task_runs:
        _make_eval_run(eval_config, task_run.id, run_config.id)

    state = await EvalJobWorker().compute_state(params)

    assert state.total == 2
    assert state.success == 2
    assert state.is_complete is True


async def test_compute_state_ignores_other_run_config(
    resolve_project, task, eval_config, run_config, data_source, params
):
    task_runs = [_make_task_run(task, data_source, "eval_set") for _ in range(2)]
    # Scored under a different run config — must not be counted.
    _make_eval_run(eval_config, task_runs[0].id, "some_other_run_config")

    state = await EvalJobWorker().compute_state(params)

    assert state.total == 2
    assert state.success == 0
    assert state.is_complete is False


async def test_compute_state_ignores_scored_items_out_of_filter(
    resolve_project, task, eval_config, run_config, data_source, params
):
    # Two items in the eval-set filter, both scored.
    in_filter = [_make_task_run(task, data_source, "eval_set") for _ in range(2)]
    for task_run in in_filter:
        _make_eval_run(eval_config, task_run.id, run_config.id)

    # An item that was scored under this run config but is NOT in the eval-set
    # filter (e.g. it drifted out / was tagged differently). EvalRunner would
    # never work it, so it must not count toward success or flip is_complete.
    out_of_filter = _make_task_run(task, data_source, "other")
    _make_eval_run(eval_config, out_of_filter.id, run_config.id)

    state = await EvalJobWorker().compute_state(params)

    # total reflects only in-filter items; the out-of-filter scored item is
    # neither counted in total nor in success.
    assert state.total == 2
    assert state.success == 2
    assert state.is_complete is True


async def test_compute_state_out_of_filter_does_not_short_circuit(
    resolve_project, task, eval_config, run_config, data_source, params
):
    # Three in-filter items; only one scored. Two remain to be worked.
    in_filter = [_make_task_run(task, data_source, "eval_set") for _ in range(3)]
    _make_eval_run(eval_config, in_filter[0].id, run_config.id)

    # Extra scored items that are out-of-filter. A naive count would inflate
    # success to 3 and falsely report is_complete, short-circuiting a resume.
    for _ in range(5):
        out_of_filter = _make_task_run(task, data_source, "other")
        _make_eval_run(eval_config, out_of_filter.id, run_config.id)

    state = await EvalJobWorker().compute_state(params)

    assert state.total == 3
    assert state.success == 1
    assert state.is_complete is False


async def test_compute_state_missing_eval_config_raises(
    resolve_project, task, run_config, data_source
):
    # No EvalConfig (or Eval) with this id exists on disk: the entity loader
    # raises rather than silently reporting "no progress", so the failure is
    # visible to the registry during reconciliation.
    bad_params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="missing_eval",
        eval_config_id="missing_eval_config",
        run_config_id="run_config1",
    )

    with pytest.raises(Exception):
        await EvalJobWorker().compute_state(bad_params)


# -- run ---------------------------------------------------------------------


async def test_run_maps_progress_and_returns_result(
    resolve_project, task, eval_config, run_config, data_source, params
):
    progresses = [
        Progress(complete=0, total=3, errors=0),
        Progress(complete=1, total=3, errors=0),
        Progress(complete=2, total=3, errors=1),
    ]

    reported: list[tuple[int, int, int | None]] = []

    class FakeCtx:
        job_id = "j_test"
        run_id = "run_test"

        async def report_progress(self, success, error=0, total=None, message=None):
            reported.append((success, error, total))

        async def report_error(self, error_message, **extra):
            pass

    with _stub_eval_runner_run(progresses):
        result = await EvalJobWorker().run(params, FakeCtx())

    assert reported == [(0, 0, 3), (1, 0, 3), (2, 1, 3)]
    assert result == EvalJobResult(total=3, success=2, error=1)


async def test_run_no_items_returns_zero_summary(
    resolve_project, task, eval_config, run_config, data_source, params
):
    class FakeCtx:
        job_id = "j_test"
        run_id = "run_test"

        async def report_progress(self, success, error=0, total=None, message=None):
            pass

        async def report_error(self, error_message, **extra):
            pass

    # Real EvalRunner with an empty dataset yields only the initial Progress(0,0,0).
    result = await EvalJobWorker().run(params, FakeCtx())

    assert result == EvalJobResult(total=0, success=0, error=0)


async def test_run_idempotent_skips_already_scored(
    resolve_project, task, eval_config, run_config, data_source, params
):
    task_runs = [_make_task_run(task, data_source, "eval_set") for _ in range(3)]
    # Two of three already scored.
    _make_eval_run(eval_config, task_runs[0].id, run_config.id)
    _make_eval_run(eval_config, task_runs[1].id, run_config.id)

    processed_dataset_ids: list = []

    async def fake_run_job(self, job) -> bool:
        processed_dataset_ids.append(job.item.id)
        EvalRun(
            parent=job.eval_config,
            dataset_id=job.item.id,
            task_run_config_id=job.task_run_config.id,
            input="test",
            output="test",
            scores={"accuracy": 1.0},
        ).save_to_file()
        return True

    class FakeCtx:
        job_id = "j_test"
        run_id = "run_test"

        async def report_progress(self, success, error=0, total=None, message=None):
            pass

        async def report_error(self, error_message, **extra):
            pass

    with patch(
        "kiln_ai.adapters.eval.eval_runner.EvalRunner.run_job",
        new=fake_run_job,
    ):
        result = await EvalJobWorker().run(params, FakeCtx())

    # Only the single not-yet-scored item should have been processed.
    assert processed_dataset_ids == [task_runs[2].id]
    # Totals are reported against the FULL eval-set size (3), not just the work
    # remaining for this run. Two were already scored (baseline), one processed.
    assert result.total == 3
    assert result.success == 3

    # No duplicate EvalRuns: three task runs, three EvalRuns total.
    assert len(eval_config.runs(readonly=True)) == 3


async def test_run_reports_full_set_totals_on_partial_resume(
    resolve_project, task, eval_config, run_config, data_source, params
):
    # 5-item eval set, 2 already scored (baseline). The stubbed runner only sees
    # the remaining 3 items, so its Progress.total is 3 — but the worker must add
    # the baseline back and report against the full set of 5.
    task_runs = [_make_task_run(task, data_source, "eval_set") for _ in range(5)]
    _make_eval_run(eval_config, task_runs[0].id, run_config.id)
    _make_eval_run(eval_config, task_runs[1].id, run_config.id)

    # EvalRunner.run() yields counts relative to the unfinished remainder (3).
    progresses = [
        Progress(complete=0, total=3, errors=0),
        Progress(complete=1, total=3, errors=0),
        Progress(complete=2, total=3, errors=0),
        Progress(complete=3, total=3, errors=0),
    ]

    reported: list[tuple[int, int, int | None]] = []

    class FakeCtx:
        job_id = "j_test"
        run_id = "run_test"

        async def report_progress(self, success, error=0, total=None, message=None):
            reported.append((success, error, total))

        async def report_error(self, error_message, **extra):
            pass

    with _stub_eval_runner_run(progresses):
        result = await EvalJobWorker().run(params, FakeCtx())

    # Reported success = baseline (2) + complete; total = baseline (2) + 3 = 5.
    # The snapshot must not regress below the baseline of 2 already-scored items.
    assert reported == [(2, 0, 5), (3, 0, 5), (4, 0, 5), (5, 0, 5)]
    assert result == EvalJobResult(total=5, success=5, error=0)


# -- save_context wiring -----------------------------------------------------


class _NoopCtx:
    job_id = "j_test"
    run_id = "run_test"

    async def report_progress(self, success, error=0, total=None, message=None):
        pass

    async def report_error(self, error_message, **extra):
        pass


def test_build_eval_runner_passes_save_context_when_git_sync_enabled(
    resolve_project, task, eval_config, run_config, params
):
    sentinel = object()

    with patch(
        "app.desktop.studio_server.jobs.workers.eval.save_context_for_project",
        return_value=sentinel,
    ) as mock_helper:
        runner = EvalJobWorker()._build_eval_runner(params, _NoopCtx())

    mock_helper.assert_called_once_with(
        params.project_id,
        context=f"eval job {params.eval_id}/{params.run_config_id}",
    )
    # The helper's SaveContext is threaded straight into the runner.
    assert runner._save_context is sentinel


def test_build_eval_runner_defaults_to_noop_when_not_git_sync(
    resolve_project, task, eval_config, run_config, params
):
    from kiln_ai.utils.git_sync_protocols import default_save_context

    with patch(
        "app.desktop.studio_server.jobs.workers.eval.save_context_for_project",
        return_value=None,
    ) as mock_helper:
        runner = EvalJobWorker()._build_eval_runner(params, _NoopCtx())

    mock_helper.assert_called_once()
    # EvalRunner coalesces None to the no-op default_save_context.
    assert runner._save_context is default_save_context


def test_build_eval_runner_attaches_error_log_observer(
    resolve_project, task, eval_config, run_config, params
):
    """The worker must attach an observer that pipes per-item EvalRunner
    failures into the job's error log — otherwise the "View Errors" dialog
    only sees the error count, not the actual error details."""
    from app.desktop.studio_server.jobs.workers.eval import _ReportErrorObserver

    runner = EvalJobWorker()._build_eval_runner(params, _NoopCtx())

    assert any(isinstance(o, _ReportErrorObserver) for o in runner._observers), (
        f"_build_eval_runner must attach a _ReportErrorObserver. Observers: {runner._observers}"
    )


async def test_report_error_observer_writes_to_error_log():
    """The observer surfaces per-item EvalRunner errors to ctx.report_error so
    they land in the per-run error log file (and via the API → the "View
    Errors" dialog). The dataset_item_id is forwarded so the user can trace
    a failure back to the specific item that broke."""
    from app.desktop.studio_server.jobs.workers.eval import _ReportErrorObserver

    captured: list[tuple[str, dict]] = []

    class CaptureCtx:
        job_id = "j_test"
        run_id = "run_test"

        async def report_progress(self, **_kwargs):
            pass

        async def report_error(self, error_message, **extra):
            captured.append((error_message, extra))

    class _FakeItem:
        id = "ds_42"

    class _FakeJob:
        item = _FakeItem()

    observer = _ReportErrorObserver(CaptureCtx())
    await observer.on_error(_FakeJob(), RuntimeError("boom"))

    assert len(captured) == 1
    message, extra = captured[0]
    assert "ds_42" in message
    assert "boom" in message
    assert extra["dataset_item_id"] == "ds_42"
    assert extra["exception_type"] == "RuntimeError"


# -- end-to-end via registry -------------------------------------------------


async def test_eval_job_through_registry(
    resolve_project, task, eval_config, run_config, data_source, params
):
    for _ in range(2):
        _make_task_run(task, data_source, "eval_set")

    progresses = [
        Progress(complete=0, total=2, errors=0),
        Progress(complete=1, total=2, errors=0),
        Progress(complete=2, total=2, errors=0),
    ]

    registry = JobRegistry()
    registry.register_type(EvalJobWorker)

    with _stub_eval_runner_run(progresses):
        job = await registry.create("eval", params, project_id=params.project_id)
        task_handle = registry._tasks[job.id]
        await task_handle

    final = registry._jobs[job.id]
    assert final.status == BackgroundJobStatus.SUCCEEDED
    assert final.result == {"total": 2, "success": 2, "error": 0}
    assert final.progress.success == 2
    assert final.progress.total == 2
    assert final.project_id == "project1"


async def test_eval_job_missing_entity_marks_failed(
    resolve_project, task, run_config, data_source
):
    # A job whose eval/eval_config does not exist: compute_state (run during
    # reconciliation) raises, and the registry marks the job failed rather than
    # treating the missing entity as "no progress".
    bad_params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="missing_eval",
        eval_config_id="missing_eval_config",
        run_config_id="run_config1",
    )

    registry = JobRegistry()
    registry.register_type(EvalJobWorker)

    job = await registry.create("eval", bad_params, project_id="project1")
    task_handle = registry._tasks[job.id]
    await task_handle

    final = registry._jobs[job.id]
    assert final.status == BackgroundJobStatus.FAILED
    assert final.error is not None
