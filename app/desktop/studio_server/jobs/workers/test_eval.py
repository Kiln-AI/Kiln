from __future__ import annotations

from contextlib import contextmanager
from typing import AsyncIterator
from unittest.mock import patch

import pytest
from app.desktop.studio_server.jobs.models import BackgroundJobStatus
from app.desktop.studio_server.jobs.registry import JobRegistry
from app.desktop.studio_server.jobs.workers.eval import (
    EvalJobParams,
    EvalJobProperties,
    EvalJobResult,
    EvalJobWorker,
    _error_detail,
)
from kiln_ai.adapters.errors import KilnRunError
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
    async def fake_run(
        self, concurrency: int = 25, observers=None
    ) -> AsyncIterator[Progress]:
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
    # error is not derivable from entities; compute_state leaves it None so the
    # registry keeps the live count rather than clobbering it on reconcile.
    assert state.error is None
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


# -- describe ----------------------------------------------------------------


async def test_describe_returns_properties(
    resolve_project, task, eval_config, run_config, params
):
    props = await EvalJobWorker().describe(params)

    assert props == EvalJobProperties(
        eval_name="Test Eval",
        run_config_name="Test Run Config",
        run_config_model_name="gpt-4",
        run_config_model_provider="openai",
        # prompt_id "simple_prompt_builder" maps to its generator label.
        run_config_prompt_name="Basic (Zero Shot)",
        run_config_tools_count=0,
        run_config_skills_count=0,
        judge_name="Test Eval Config",
        # EvalConfig.config_type defaults to g_eval.
        judge_algorithm="g_eval",
        judge_model_name="gpt-4",
        judge_model_provider="openai",
    )


async def test_describe_counts_tools_skills_and_frozen_prompt(
    resolve_project, task, eval, eval_config, data_source
):
    # A run config with a frozen prompt, one regular tool, and two skills.
    from kiln_ai.datamodel.prompt import BasePrompt
    from kiln_ai.datamodel.run_config import ToolsRunConfig

    run_config = TaskRunConfig(
        id="run_config_tools",
        name="Tools Run Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="task_run_config::p::t::frozen1",
            structured_output_mode=StructuredOutputMode.json_schema,
            tools_config=ToolsRunConfig(
                tools=[
                    "kiln_tool::add_numbers",
                    "kiln_tool::skill::abc",
                    "kiln_tool::skill::def",
                ],
            ),
        ),
        prompt=BasePrompt(name="Frozen Prompt", prompt="do it"),
        parent=task,
    )
    run_config.save_to_file()

    params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="eval1",
        eval_config_id="eval_config1",
        run_config_id="run_config_tools",
    )

    props = await EvalJobWorker().describe(params)

    assert props.run_config_prompt_name == "Frozen Prompt"
    assert props.run_config_tools_count == 1
    assert props.run_config_skills_count == 2


async def test_describe_resolves_custom_prompt_name(
    resolve_project, task, eval, eval_config, data_source
):
    # A custom prompt saved under the task, referenced by "id::<prompt_id>".
    from kiln_ai.datamodel.prompt import Prompt

    prompt = Prompt(id="myprompt", name="My Custom Prompt", prompt="do it", parent=task)
    prompt.save_to_file()

    run_config = TaskRunConfig(
        id="run_config_custom_prompt",
        name="Custom Prompt Run Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="id::myprompt",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()

    params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="eval1",
        eval_config_id="eval_config1",
        run_config_id="run_config_custom_prompt",
    )

    props = await EvalJobWorker().describe(params)

    # Resolved to the saved name, not the raw "id::myprompt".
    assert props.run_config_prompt_name == "My Custom Prompt"


async def test_describe_resolves_reused_frozen_prompt_name(
    resolve_project, task, eval, eval_config, data_source
):
    # One run config carries a frozen prompt; a second run config reuses it via
    # a "task_run_config::<proj>::<task>::<run_config_id>" prompt_id and has no
    # own prompt — exercising the cross-run-config resolution branch.
    from kiln_ai.datamodel.prompt import BasePrompt

    owner = TaskRunConfig(
        id="frozen_owner",
        name="Frozen Owner",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        prompt=BasePrompt(name="Shared Frozen Prompt", prompt="do it"),
        parent=task,
    )
    owner.save_to_file()

    reuser = TaskRunConfig(
        id="frozen_reuser",
        name="Frozen Reuser",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="task_run_config::project1::task1::frozen_owner",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    reuser.save_to_file()

    params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="eval1",
        eval_config_id="eval_config1",
        run_config_id="frozen_reuser",
    )

    props = await EvalJobWorker().describe(params)

    # Resolved from the owning run config's frozen prompt, not the raw id.
    assert props.run_config_prompt_name == "Shared Frozen Prompt"


async def test_describe_resolves_fine_tune_prompt_name(
    resolve_project, task, eval, eval_config, data_source
):
    run_config = TaskRunConfig(
        id="run_config_finetune",
        name="Fine-Tune Run Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="fine_tune_prompt::project1::task1::ft123",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()

    params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="eval1",
        eval_config_id="eval_config1",
        run_config_id="run_config_finetune",
    )

    props = await EvalJobWorker().describe(params)

    assert props.run_config_prompt_name == "Fine-Tune Prompt"


async def test_describe_falls_back_to_raw_id_when_unresolvable(
    resolve_project, task, eval, eval_config, data_source
):
    # An "id::" prompt referencing a prompt that doesn't exist on the task — the
    # resolver exhausts every branch and falls back to the raw id rather than
    # raising.
    run_config = TaskRunConfig(
        id="run_config_missing_prompt",
        name="Missing Prompt Run Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="id::doesnotexist",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()

    params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="eval1",
        eval_config_id="eval_config1",
        run_config_id="run_config_missing_prompt",
    )

    props = await EvalJobWorker().describe(params)

    assert props.run_config_prompt_name == "id::doesnotexist"


async def test_describe_mcp_run_config_blanks_agent_fields(
    resolve_project, task, eval, eval_config, data_source
):
    # An MCP (agentless) run config has no model/prompt/tools. describe() must
    # still return valid properties — eval/judge info intact, agent fields blank.
    from kiln_ai.datamodel.run_config import (
        MCPToolReference,
        McpRunConfigProperties,
    )

    run_config = TaskRunConfig(
        id="run_config_mcp",
        name="MCP Run Config",
        run_config_properties=McpRunConfigProperties(
            tool_reference=MCPToolReference(
                tool_id="mcp::local::my_server::my_tool",
                tool_name="my_tool",
            ),
        ),
        parent=task,
    )
    run_config.save_to_file()

    params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="eval1",
        eval_config_id="eval_config1",
        run_config_id="run_config_mcp",
    )

    props = await EvalJobWorker().describe(params)

    # Eval/judge info preserved; agent-specific fields blanked, counts zeroed.
    assert props.eval_name == "Test Eval"
    assert props.run_config_name == "MCP Run Config"
    assert props.judge_name == "Test Eval Config"
    assert props.run_config_model_name == ""
    assert props.run_config_model_provider == ""
    assert props.run_config_prompt_name == ""
    assert props.run_config_tools_count == 0
    assert props.run_config_skills_count == 0


async def test_describe_missing_entity_raises(resolve_project, task, run_config):
    # Mirrors compute_state: the entity loader raises rather than silently
    # returning partial info. The registry guard (_describe) swallows this.
    bad_params = EvalJobParams(
        project_id="project1",
        task_id="task1",
        eval_id="missing_eval",
        eval_config_id="missing_eval_config",
        run_config_id="run_config1",
    )

    with pytest.raises(Exception):
        await EvalJobWorker().describe(bad_params)


async def test_registry_create_populates_properties(
    resolve_project, task, eval_config, run_config, params
):
    registry = JobRegistry()
    registry.register_type(EvalJobWorker)

    job = await registry.create("eval", params, project_id=params.project_id)
    await registry._tasks[job.id]

    assert job.properties == {
        "eval_name": "Test Eval",
        "run_config_name": "Test Run Config",
        "run_config_model_name": "gpt-4",
        "run_config_model_provider": "openai",
        "run_config_prompt_name": "Basic (Zero Shot)",
        "run_config_tools_count": 0,
        "run_config_skills_count": 0,
        "judge_name": "Test Eval Config",
        "judge_algorithm": "g_eval",
        "judge_model_name": "gpt-4",
        "judge_model_provider": "openai",
    }


async def test_registry_create_guards_describe_failure(
    resolve_project, task, run_config
):
    # describe() raises (eval/eval_config missing): create must still succeed,
    # leaving properties unset rather than failing the whole job creation.
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
    await registry._tasks[job.id]

    assert job.properties is None


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


async def test_run_logs_failed_items_to_error_log(
    resolve_project, task, eval_config, run_config, data_source, params
):
    # An in-filter item whose eval job raises: the worker's observer must forward
    # the exception to ctx.report_error so /api/jobs/{id}/errors is populated —
    # progress.errors is only a count, not the messages.
    task_run = _make_task_run(task, data_source, "eval_set")

    async def failing_run_job(self, job) -> bool:
        raise ValueError("scoring exploded")

    logged: list[tuple[str, dict]] = []

    class FakeCtx:
        job_id = "j_test"
        run_id = "run_test"

        async def report_progress(self, success, error=0, total=None, message=None):
            pass

        async def report_error(self, error_message, **extra):
            logged.append((error_message, extra))

    with patch(
        "kiln_ai.adapters.eval.eval_runner.EvalRunner.run_job",
        new=failing_run_job,
    ):
        result = await EvalJobWorker().run(params, FakeCtx())

    assert result.error == 1
    assert len(logged) == 1
    message, extra = logged[0]
    assert "scoring exploded" in message
    assert extra["dataset_id"] == task_run.id
    assert extra["run_config_id"] == run_config.id


@pytest.mark.asyncio
async def test_run_logs_original_error_for_kiln_run_error(
    resolve_project, task, eval_config, run_config, data_source, params
):
    # The model adapter wraps failures in KilnRunError, whose own message is the
    # genericized format_error_message text. The error log must surface the
    # underlying .original detail, not "An unexpected error occurred."
    _make_task_run(task, data_source, "eval_set")

    original = RuntimeError("provider 500: model is overloaded right now")

    async def failing_run_job(self, job) -> bool:
        raise KilnRunError(
            message="An unexpected error occurred.",
            partial_trace=None,
            original=original,
        )

    logged: list[tuple[str, dict]] = []

    class FakeCtx:
        job_id = "j_test"
        run_id = "run_test"

        async def report_progress(self, success, error=0, total=None, message=None):
            pass

        async def report_error(self, error_message, **extra):
            logged.append((error_message, extra))

    with patch(
        "kiln_ai.adapters.eval.eval_runner.EvalRunner.run_job",
        new=failing_run_job,
    ):
        result = await EvalJobWorker().run(params, FakeCtx())

    assert result.error == 1
    assert len(logged) == 1
    message, _ = logged[0]
    assert message == "provider 500: model is overloaded right now"
    assert "An unexpected error occurred." not in message


def test_error_detail_unwraps_kiln_run_error():
    original = ValueError("real underlying detail")
    wrapped = KilnRunError(
        message="An unexpected error occurred.",
        partial_trace=None,
        original=original,
    )
    assert _error_detail(wrapped) == "real underlying detail"


def test_error_detail_falls_back_to_original_class_name_when_empty():
    original = RuntimeError("")
    wrapped = KilnRunError(
        message="An unexpected error occurred.",
        partial_trace=None,
        original=original,
    )
    assert _error_detail(wrapped) == "RuntimeError"


def test_error_detail_passes_through_plain_exception():
    assert _error_detail(ValueError("scoring exploded")) == "scoring exploded"


def test_error_detail_falls_back_to_class_name_for_empty_plain_exception():
    assert _error_detail(ValueError("")) == "ValueError"


def test_error_detail_does_not_crash_on_buggy_str():
    # The observer runs in AsyncJobRunner's unguarded on_error path, so a buggy
    # __str__ must degrade to the class name rather than take down the run.
    class BoomError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("str blew up")

    assert _error_detail(BoomError()) == "BoomError"


def test_error_detail_handles_kiln_run_error_with_buggy_original_str():
    class BoomError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("str blew up")

    wrapped = KilnRunError(
        message="An unexpected error occurred.",
        partial_trace=None,
        original=BoomError(),
    )
    assert _error_detail(wrapped) == "BoomError"


# -- save_context wiring -----------------------------------------------------


def test_build_eval_runner_passes_save_context_when_git_sync_enabled(
    resolve_project, task, eval_config, run_config, params
):
    sentinel = object()

    with patch(
        "app.desktop.studio_server.jobs.workers.eval.save_context_for_project",
        return_value=sentinel,
    ) as mock_helper:
        runner = EvalJobWorker()._build_eval_runner(params)

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
        runner = EvalJobWorker()._build_eval_runner(params)

    mock_helper.assert_called_once()
    # EvalRunner coalesces None to the no-op default_save_context.
    assert runner._save_context is default_save_context


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
    # A job whose eval/eval_config does not exist marks failed. The launch-time
    # reconcile swallows compute_state's exception (best-effort, falls back to
    # last-known state), but run() then calls compute_state for its baseline,
    # which raises and is caught by _supervise -> the job fails rather than
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
