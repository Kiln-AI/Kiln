import random
from typing import Callable, Dict

import pytest

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.judge_job_runner import (
    JudgeJobRunner,
    example_fails,
    feedback_from_intermediate_outputs,
    score_passes,
)
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    JudgeJob,
    JudgeJobRun,
    JudgeJobStatus,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalScores,
)


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
def mock_task(tmp_path):
    task = Task(
        name="test",
        instruction="do the thing",
        path=tmp_path / "task.kiln",
    )
    task.save_to_file()
    return task


def make_eval(task, score_type=TaskOutputRatingType.pass_fail, name="Accuracy"):
    eval = Eval(
        name="e",
        eval_set_filter_id="all",
        eval_configs_filter_id="all",
        output_scores=[EvalOutputScore(name=name, type=score_type)],
        parent=task,
    )
    eval.save_to_file()
    return eval


def make_eval_config(eval):
    eval_config = EvalConfig(
        name="c",
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        parent=eval,
        properties={"eval_steps": ["step1"]},
    )
    eval_config.save_to_file()
    return eval_config


def make_judge_job(
    task, eval_config, target_tags=None, count=2, max_samples=10, threshold=0.75
):
    job = JudgeJob(
        name="scan",
        target_tags=target_tags if target_tags is not None else ["train"],
        eval_config_id=eval_config.id,
        count=count,
        max_samples=max_samples,
        threshold=threshold,
        parent=task,
    )
    job.save_to_file()
    return job


def make_train_run(task, data_source, input_text, tags=None):
    run = TaskRun(
        parent=task,
        input=input_text,
        input_source=data_source,
        output=TaskOutput(output=f"output for {input_text}"),
        tags=tags if tags is not None else ["train"],
    )
    run.save_to_file()
    return run


def scripted_evaluator_factory(
    score_fn: Callable[[TaskRun], EvalScores],
    calls: list[str] | None = None,
    feedback: Dict[str, str] | None = None,
):
    class ScriptedEvaluator(BaseEval):
        async def run_eval(self, task_run, eval_job_item=None):
            if calls is not None:
                calls.append(task_run.id)
            return score_fn(task_run), (
                feedback
                if feedback is not None
                else {"chain_of_thought": f"reasoning for {task_run.input}"}
            )

        async def run_task_and_eval(self, eval_job_item):
            raise AssertionError("run_task_and_eval should not be called")

    return lambda *args, **kwargs: ScriptedEvaluator(*args, **kwargs)


async def run_job(judge_job, eval_config, score_fn, calls=None, seed=1, concurrency=25):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.judge_job_runner.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn, calls=calls),
        )
        runner = JudgeJobRunner(judge_job, eval_config, rng=random.Random(seed))
        progresses = [p async for p in runner.run(concurrency=concurrency)]
    return progresses


# ---- Pure helper tests ----


def test_score_passes_rating_types():
    assert score_passes(4.0, TaskOutputRatingType.five_star, 0.75) is True
    assert score_passes(3.0, TaskOutputRatingType.five_star, 0.75) is False
    assert score_passes(1.0, TaskOutputRatingType.pass_fail, 0.75) is True
    assert score_passes(0.0, TaskOutputRatingType.pass_fail, 0.75) is False
    assert score_passes(1.0, TaskOutputRatingType.pass_fail_critical, 0.75) is True
    assert score_passes(0.0, TaskOutputRatingType.pass_fail_critical, 0.75) is False


def test_example_fails_requires_all_scores_below_bar():
    output_scores = [
        EvalOutputScore(name="Accuracy", type=TaskOutputRatingType.pass_fail),
        EvalOutputScore(name="Quality", type=TaskOutputRatingType.five_star),
    ]
    assert example_fails({"accuracy": 0.0, "quality": 2.0}, output_scores, 0.75) is True
    assert (
        example_fails({"accuracy": 1.0, "quality": 2.0}, output_scores, 0.75) is False
    )


def test_example_fails_with_missing_scores():
    output_scores = [
        EvalOutputScore(name="Accuracy", type=TaskOutputRatingType.pass_fail),
        EvalOutputScore(name="Quality", type=TaskOutputRatingType.five_star),
    ]
    assert example_fails({"accuracy": 0.0}, output_scores, 0.75) is True
    assert example_fails({"accuracy": 1.0}, output_scores, 0.75) is False


def test_feedback_from_intermediate_outputs():
    assert feedback_from_intermediate_outputs(None) is None
    assert feedback_from_intermediate_outputs({"reasoning": "  r  "}) == "r"
    assert (
        feedback_from_intermediate_outputs(
            {"chain_of_thought": "cot", "reasoning": "r"}
        )
        == "r"
    )


# ---- Runner construction ----


def test_runner_requires_parents(mock_task):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config)

    # eval config with no parent eval
    orphan_config = EvalConfig(
        name="c",
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["s"]},
    )
    with pytest.raises(ValueError, match="parent eval"):
        JudgeJobRunner(job, orphan_config)


# ---- Orchestration ----


@pytest.mark.asyncio
async def test_persists_runs_status_and_outcome(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config, count=2, max_samples=10)

    fail_ids = {
        make_train_run(mock_task, data_source, f"fail-{i}").id for i in range(3)
    }
    for i in range(3):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0 if task_run.input.startswith("fail") else 1.0}

    await run_job(job, eval_config, score_fn)

    assert job.latest_status == JudgeJobStatus.succeeded
    assert job.outcome is not None
    assert job.outcome.train_set_size == 6
    assert job.outcome.failing_count == 3
    assert job.outcome.hit_cap is False

    runs = job.runs()
    assert len(runs) == 6
    failing = [r for r in runs if not r.passed]
    assert {r.dataset_id for r in failing} == fail_ids
    assert all(r.feedback for r in failing)


@pytest.mark.asyncio
async def test_early_stop_limits_num_judged(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config, count=2, max_samples=10)
    for i in range(10):
        make_train_run(mock_task, data_source, f"fail-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0}

    # concurrency=1 so we can stop exactly at count
    await run_job(job, eval_config, score_fn, concurrency=1)

    assert job.latest_status == JudgeJobStatus.succeeded
    assert job.outcome.num_judged == 2
    assert job.outcome.failing_count == 2
    assert job.outcome.hit_cap is False
    assert len(job.runs()) == 2


@pytest.mark.asyncio
async def test_hit_cap_when_failures_sparse(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config, count=2, max_samples=5)
    for i in range(5):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 1.0}

    await run_job(job, eval_config, score_fn)

    assert job.outcome.num_judged == 5
    assert job.outcome.failing_count == 0
    assert job.outcome.hit_cap is True


@pytest.mark.asyncio
async def test_exhausted_train_set_is_not_hit_cap(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config, count=2, max_samples=10)
    for i in range(3):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 1.0}

    await run_job(job, eval_config, score_fn)

    assert job.outcome.num_judged == 3
    assert job.outcome.hit_cap is False


@pytest.mark.asyncio
async def test_tag_filtering_and_semantics(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    # require BOTH tags
    job = make_judge_job(
        mock_task, eval_config, target_tags=["train", "golden"], count=5, max_samples=10
    )

    both = make_train_run(mock_task, data_source, "both", tags=["train", "golden"])
    make_train_run(mock_task, data_source, "train-only", tags=["train"])
    make_train_run(mock_task, data_source, "other", tags=["other"])

    def score_fn(task_run):
        return {"accuracy": 0.0}

    await run_job(job, eval_config, score_fn)

    assert job.outcome.train_set_size == 1
    assert job.outcome.num_judged == 1
    runs = job.runs()
    assert len(runs) == 1
    assert runs[0].dataset_id == both.id


@pytest.mark.asyncio
async def test_cache_reuse_skips_judging(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config, count=1, max_samples=1)
    run = make_train_run(mock_task, data_source, "fail-0")

    # Pre-seed a judged result for this item
    JudgeJobRun(
        parent=job,
        dataset_id=run.id,
        scores={"accuracy": 0.0},
        feedback="cached",
        passed=False,
    ).save_to_file()

    calls: list[str] = []

    def score_fn(task_run):
        return {"accuracy": 0.0}

    await run_job(job, eval_config, score_fn, calls=calls)

    # Judge was never invoked; no duplicate run written
    assert calls == []
    assert len(job.runs()) == 1
    assert job.outcome.failing_count == 1


@pytest.mark.asyncio
async def test_threshold_override_five_star(mock_task, data_source):
    eval = make_eval(
        mock_task, score_type=TaskOutputRatingType.five_star, name="Quality"
    )
    eval_config = make_eval_config(eval)
    make_train_run(mock_task, data_source, "item-0")

    def score_fn(task_run):
        return {"quality": 4.0}  # normalized 0.75

    # Default bar 0.75: 0.75 >= 0.75 -> pass -> no failures
    job_pass = make_judge_job(
        mock_task, eval_config, count=1, max_samples=1, threshold=0.75
    )
    await run_job(job_pass, eval_config, score_fn)
    assert job_pass.outcome.failing_count == 0

    # Stricter bar 0.9: 0.75 < 0.9 -> fail
    job_fail = make_judge_job(
        mock_task, eval_config, count=1, max_samples=1, threshold=0.9
    )
    await run_job(job_fail, eval_config, score_fn)
    assert job_fail.outcome.failing_count == 1


@pytest.mark.asyncio
async def test_judge_errors_are_skipped(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config, count=2, max_samples=2)
    make_train_run(mock_task, data_source, "error-item")
    fail_run = make_train_run(mock_task, data_source, "fail-item")

    def score_fn(task_run):
        if task_run.input == "error-item":
            raise RuntimeError("Judge error")
        return {"accuracy": 0.0}

    await run_job(job, eval_config, score_fn)

    assert job.latest_status == JudgeJobStatus.succeeded
    assert job.outcome.num_judged == 2
    runs = job.runs()
    # The errored item is skipped (not persisted); only the failing item has a run
    assert len(runs) == 1
    assert runs[0].dataset_id == fail_run.id
    assert runs[0].passed is False


@pytest.mark.asyncio
async def test_run_cancelled_sets_status(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_job(mock_task, eval_config, count=2, max_samples=10)
    for i in range(5):
        make_train_run(mock_task, data_source, f"fail-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.judge_job_runner.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        runner = JudgeJobRunner(job, eval_config, rng=random.Random(1))
        gen = runner.run(concurrency=1)
        await gen.__anext__()  # first progress yield; status is now running
        assert job.latest_status == JudgeJobStatus.running
        await gen.aclose()  # raises GeneratorExit into the generator

    assert job.latest_status == JudgeJobStatus.cancelled
    assert job.outcome is not None
    assert job.outcome.error == "Run cancelled"
