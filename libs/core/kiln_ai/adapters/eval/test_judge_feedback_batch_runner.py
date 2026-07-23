# TODO (merge blocker — do not merge toward main until resolved): tests for a runner under design
# review — see the header of kiln_ai/datamodel/judge_feedback_batch.py. Resolve before merging
# toward main.

import random
from typing import Callable, Dict

import pytest

from kiln_ai.adapters.eval import judge_feedback_batch_runner
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.judge_feedback_batch_runner import (
    JudgeFeedbackBatchRunner,
    aggregate_usage,
    example_fails,
    feedback_from_intermediate_outputs,
    score_passes,
)
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    JudgeFeedbackBatch,
    JudgeFeedbackBatchRun,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalOutputScore,
    EvalScores,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode, TaskRunConfig
from kiln_ai.datamodel.usage import Usage


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


def make_judge_feedback_batch(
    task,
    eval_config,
    target_tags=None,
    stop_after_failures=2,
    max_samples=10,
    threshold=0.75,
):
    job = JudgeFeedbackBatch(
        name="scan",
        target_tags=target_tags if target_tags is not None else ["train"],
        eval_config_id=eval_config.id,
        stop_after_failures=stop_after_failures,
        max_samples=max_samples,
        threshold=threshold,
        parent=task,
    )
    job.save_to_file()
    return job


def make_run_config(task):
    rc = TaskRunConfig(
        name="candidate",
        description="candidate",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    rc.save_to_file()
    return rc


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
    generate: bool = False,
    fresh_usage: Usage | None = None,
):
    def _feedback(task_run):
        return (
            feedback
            if feedback is not None
            else {"chain_of_thought": f"reasoning for {task_run.input}"}
        )

    class ScriptedEvaluator(BaseEval):
        async def run_eval(self, task_run, eval_job_item=None):
            # In generate mode the runner must call run_task_and_eval, never run_eval directly.
            assert not generate, "run_eval should not be called in generate mode"
            if calls is not None:
                calls.append(task_run.id)
            return score_fn(task_run), _feedback(task_run)

        async def run_task_and_eval(self, eval_job_item):
            assert generate, "run_task_and_eval should not be called"
            if calls is not None:
                calls.append(eval_job_item.id)
            # Stand in for "ran the config to produce a fresh output, then judged it." The fresh
            # TaskRun is discarded by the runner (only its usage is kept), so a placeholder carrying
            # the scripted usage is fine here.
            fresh_run = (
                eval_job_item.model_copy(update={"usage": fresh_usage})
                if fresh_usage is not None
                else eval_job_item
            )
            return fresh_run, score_fn(eval_job_item), _feedback(eval_job_item)

    return lambda *args, **kwargs: ScriptedEvaluator(*args, **kwargs)


async def run_job(
    judge_feedback_batch,
    eval_config,
    score_fn,
    calls=None,
    seed=1,
    concurrency=25,
    max_retries=0,
    retry_delay=0,
    fresh_usage=None,
    progress_callback=None,
    error_callback=None,
):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.judge_feedback_batch_runner.legacy_eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(
                score_fn,
                calls=calls,
                generate=judge_feedback_batch.generate_outputs,
                fresh_usage=fresh_usage,
            ),
        )
        runner = JudgeFeedbackBatchRunner(
            judge_feedback_batch,
            eval_config,
            rng=random.Random(seed),
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        return await runner.run(
            concurrency=concurrency,
            progress_callback=progress_callback,
            error_callback=error_callback,
        )


# ---- Pure helper tests ----


def test_score_passes_rating_types():
    assert score_passes(4.0, TaskOutputRatingType.five_star, 0.75) is True
    assert score_passes(3.0, TaskOutputRatingType.five_star, 0.75) is False
    assert score_passes(1.0, TaskOutputRatingType.pass_fail, 0.75) is True
    assert score_passes(0.0, TaskOutputRatingType.pass_fail, 0.75) is False
    assert score_passes(1.0, TaskOutputRatingType.pass_fail_critical, 0.75) is True
    assert score_passes(0.0, TaskOutputRatingType.pass_fail_critical, 0.75) is False


def test_score_passes_non_numeric():
    # A non-numeric score can't clear the bar (and must not raise).
    assert score_passes("oops", TaskOutputRatingType.pass_fail, 0.75) is False  # type: ignore[arg-type]


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
    # non-str values are ignored, not crashed on
    assert feedback_from_intermediate_outputs({"reasoning": {"x": 1}}) is None  # type: ignore[dict-item]


# ---- Runner construction ----


def test_runner_requires_parents(mock_task):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(mock_task, eval_config)

    orphan_config = EvalConfig(
        name="c",
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["s"]},
    )
    with pytest.raises(ValueError, match="parent eval"):
        JudgeFeedbackBatchRunner(job, orphan_config)


# ---- Orchestration ----


@pytest.mark.asyncio
async def test_full_coverage_returns_all_judged_runs(mock_task, data_source):
    # Default (stop_after_failures=None) is a gate: judge the WHOLE matching set, return every
    # judged item keyed by task_run_id so the caller can pair against another run.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=10
    )

    fail_ids = {
        make_train_run(mock_task, data_source, f"fail-{i}").id for i in range(3)
    }
    for i in range(3):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0 if task_run.input.startswith("fail") else 1.0}

    result = await run_job(job, eval_config, score_fn)

    assert result.train_set_size == 6
    assert result.num_judged == 6
    assert result.failing_count == 3
    assert result.hit_cap is False
    # No early-stop, no trim: every failure is returned...
    assert len(result.failing_runs) == 3
    assert all(not r.passed for r in result.failing_runs)
    assert all(r.task_run_id in fail_ids for r in result.failing_runs)
    assert all(r.feedback for r in result.failing_runs)
    # ...and judged_runs holds all 6 (pass and fail), keyed by task_run_id.
    assert len(result.judged_runs) == 6
    assert sum(1 for r in result.judged_runs if r.passed) == 3
    assert {r.task_run_id for r in result.judged_runs} == {
        r.id for r in mock_task.runs()
    }

    # All judged items persisted as children (pass and fail)
    assert len(job.runs()) == 6


@pytest.mark.asyncio
async def test_progress_callback_streams_per_chunk(mock_task, data_source):
    # The callback fires once per chunk with (num_judged, error_count, planned_total),
    # where planned_total is the capped matching-set size, so a job can stream progress.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=10
    )
    for i in range(5):
        make_train_run(mock_task, data_source, f"item-{i}")

    ticks: list[tuple[int, int, int]] = []

    async def on_progress(num_judged, error_count, planned_total):
        ticks.append((num_judged, error_count, planned_total))

    # concurrency=2 over 5 items -> chunks of 2,2,1 -> 3 ticks, num_judged monotone.
    result = await run_job(
        job,
        eval_config,
        lambda tr: {"accuracy": 1.0},
        concurrency=2,
        progress_callback=on_progress,
    )

    assert result.num_judged == 5
    assert [t[0] for t in ticks] == [2, 4, 5]
    assert all(t[1] == 0 for t in ticks)
    # planned_total is the capped set (min(train_set_size, max_samples) = 5).
    assert all(t[2] == 5 for t in ticks)


@pytest.mark.asyncio
async def test_stop_after_failures_trims_minibatch(mock_task, data_source):
    # Train-signal mode: stop_after_failures caps the returned minibatch; judged_runs still holds
    # everything judged this chunk.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=2, max_samples=10
    )

    for i in range(3):
        make_train_run(mock_task, data_source, f"fail-{i}")
    for i in range(3):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0 if task_run.input.startswith("fail") else 1.0}

    # concurrency 25 judges all 6 in one chunk, so all failures are found before the early-stop check
    result = await run_job(job, eval_config, score_fn)

    assert result.failing_count == 3
    assert len(result.failing_runs) == 2  # trimmed to stop_after_failures
    assert len(result.judged_runs) == 6


@pytest.mark.asyncio
async def test_early_stop_limits_num_judged(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=2, max_samples=10
    )
    for i in range(10):
        make_train_run(mock_task, data_source, f"fail-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0}

    result = await run_job(job, eval_config, score_fn, concurrency=1)

    assert result.num_judged == 2
    assert result.failing_count == 2
    assert result.hit_cap is False
    assert len(job.runs()) == 2


@pytest.mark.asyncio
async def test_hit_cap_when_failures_sparse(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=2, max_samples=5
    )
    for i in range(5):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 1.0}

    result = await run_job(job, eval_config, score_fn)

    assert result.num_judged == 5
    assert result.failing_count == 0
    assert result.hit_cap is True
    assert result.failing_runs == []


@pytest.mark.asyncio
async def test_gate_mode_hit_cap_when_set_exceeds_max_samples(mock_task, data_source):
    # Gate mode (stop_after_failures=None) with more matching items than max_samples: judge exactly
    # max_samples, report hit_cap=True (coverage was capped), and select deterministically so the
    # capped subset is stable/pairable across runs.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=3
    )
    for i in range(8):
        make_train_run(mock_task, data_source, f"item-{i}")

    result = await run_job(job, eval_config, lambda tr: {"accuracy": 1.0})

    assert result.train_set_size == 8
    assert result.num_judged == 3
    assert result.hit_cap is True
    assert len(result.judged_runs) == 3

    # Deterministic (sorted-by-id) capping: a second identical run covers the SAME task_run_ids.
    job2 = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=3
    )
    result2 = await run_job(job2, eval_config, lambda tr: {"accuracy": 1.0}, seed=999)
    assert {r.task_run_id for r in result.judged_runs} == {
        r.task_run_id for r in result2.judged_runs
    }


@pytest.mark.asyncio
async def test_empty_candidate_set(mock_task, data_source):
    # No dataset item carries the target tags: the chunk loop never runs, so counts are zero, all
    # aggregate signals are None/empty, hit_cap is False, and no callback fires.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, target_tags=["nonexistent"], stop_after_failures=None
    )
    make_train_run(mock_task, data_source, "item-0", tags=["other"])

    ticks: list[tuple[int, int, int]] = []

    async def on_progress(*args):
        ticks.append(args)

    result = await run_job(
        job, eval_config, lambda tr: {"accuracy": 1.0}, progress_callback=on_progress
    )

    assert result.train_set_size == 0
    assert result.num_judged == 0
    assert result.failing_count == 0
    assert result.hit_cap is False
    assert result.judged_runs == []
    assert result.failing_runs == []
    assert result.errors == []
    assert result.mean_normalized_scores == {}
    assert result.mean_normalized_score is None
    assert result.total_usage is None
    assert ticks == []


@pytest.mark.asyncio
async def test_exhausted_train_set_is_not_hit_cap(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=2, max_samples=10
    )
    for i in range(3):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 1.0}

    result = await run_job(job, eval_config, score_fn)

    assert result.num_judged == 3
    assert result.hit_cap is False


@pytest.mark.asyncio
async def test_tag_filtering_and_semantics(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task,
        eval_config,
        target_tags=["train", "golden"],
        stop_after_failures=5,
        max_samples=10,
    )

    both = make_train_run(mock_task, data_source, "both", tags=["train", "golden"])
    make_train_run(mock_task, data_source, "train-only", tags=["train"])
    make_train_run(mock_task, data_source, "other", tags=["other"])

    def score_fn(task_run):
        return {"accuracy": 0.0}

    result = await run_job(job, eval_config, score_fn)

    assert result.train_set_size == 1
    assert result.num_judged == 1
    assert len(result.failing_runs) == 1
    assert result.failing_runs[0].task_run_id == both.id


@pytest.mark.asyncio
async def test_cache_reuse_skips_judging(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1
    )
    run = make_train_run(mock_task, data_source, "fail-0")

    JudgeFeedbackBatchRun(
        parent=job,
        task_run_id=run.id,
        scores={"accuracy": 0.0},
        feedback="cached",
        passed=False,
    ).save_to_file()

    calls: list[str] = []

    def score_fn(task_run):
        return {"accuracy": 0.0}

    result = await run_job(job, eval_config, score_fn, calls=calls)

    # Judge was never invoked; no duplicate run written
    assert calls == []
    assert len(job.runs()) == 1
    assert result.failing_count == 1
    assert result.failing_runs[0].feedback == "cached"


@pytest.mark.asyncio
async def test_threshold_override_five_star(mock_task, data_source):
    eval = make_eval(
        mock_task, score_type=TaskOutputRatingType.five_star, name="Quality"
    )
    eval_config = make_eval_config(eval)
    make_train_run(mock_task, data_source, "item-0")

    def score_fn(task_run):
        return {"quality": 4.0}  # normalized 0.75

    job_pass = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1, threshold=0.75
    )
    result_pass = await run_job(job_pass, eval_config, score_fn)
    assert result_pass.failing_count == 0

    job_fail = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1, threshold=0.9
    )
    result_fail = await run_job(job_fail, eval_config, score_fn)
    assert result_fail.failing_count == 1


@pytest.mark.asyncio
async def test_error_callback_fires_live_not_batched(mock_task, data_source):
    # Regression: errors must be delivered to error_callback as they happen (interleaved with
    # progress), not all at the end — otherwise a job's "View Errors" shows nothing mid-run.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    # Gate mode, one item per chunk, so the error in chunk 1 must be reported before chunk 2's
    # progress tick.
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=10
    )
    make_train_run(mock_task, data_source, "error-item")
    make_train_run(mock_task, data_source, "ok-item")

    def score_fn(task_run):
        if task_run.input == "error-item":
            raise RuntimeError("boom")
        return {"accuracy": 1.0}

    events: list[str] = []

    async def on_progress(num_judged, error_count, planned_total):
        events.append(f"progress:{num_judged}")

    async def on_error(item_error):
        events.append(f"error:{item_error.task_run_id}")

    result = await run_job(
        job,
        eval_config,
        score_fn,
        concurrency=1,
        progress_callback=on_progress,
        error_callback=on_error,
    )

    # The error is collected once and surfaced through the callback.
    assert len(result.errors) == 1
    error_events = [e for e in events if e.startswith("error:")]
    assert len(error_events) == 1
    assert "boom" in result.errors[0].error
    # Live delivery: the error event lands before the LAST progress tick (both items examined),
    # i.e. it was not deferred until after the run completed.
    assert events.index(error_events[0]) < len(events) - 1
    assert events[-1] == "progress:2"


@pytest.mark.asyncio
async def test_judge_errors_are_collected_and_skipped(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=2, max_samples=2
    )
    error_run = make_train_run(mock_task, data_source, "error-item")
    fail_run = make_train_run(mock_task, data_source, "fail-item")

    def score_fn(task_run):
        if task_run.input == "error-item":
            raise RuntimeError("Judge error")
        return {"accuracy": 0.0}

    result = await run_job(job, eval_config, score_fn)

    assert result.num_judged == 2
    # The errored item is skipped (not persisted, not in judged_runs); only the failing item has a run
    assert len(job.runs()) == 1
    assert len(result.judged_runs) == 1
    assert result.judged_runs[0].task_run_id == fail_run.id
    assert len(result.failing_runs) == 1
    assert result.failing_runs[0].task_run_id == fail_run.id
    # The error is collected and surfaced (not silently swallowed) so the caller sees partial failure.
    assert len(result.errors) == 1
    assert result.errors[0].task_run_id == error_run.id
    assert "Judge error" in result.errors[0].error


@pytest.mark.asyncio
async def test_save_errors_are_collected_but_result_kept(
    mock_task, data_source, monkeypatch
):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1
    )
    fail_run = make_train_run(mock_task, data_source, "fail-item")

    def boom(self):
        raise RuntimeError("disk full")

    monkeypatch.setattr(JudgeFeedbackBatchRun, "save_to_file", boom)

    def score_fn(task_run):
        return {"accuracy": 0.0}

    result = await run_job(job, eval_config, score_fn)

    # The failing example is still returned even though persistence failed...
    assert len(result.failing_runs) == 1
    assert result.failing_runs[0].task_run_id == fail_run.id
    # ...and the save failure is reported so the caller knows the result wasn't durably stored.
    assert len(result.errors) == 1
    assert result.errors[0].task_run_id == fail_run.id
    assert "disk full" in result.errors[0].error


@pytest.mark.asyncio
async def test_transient_error_retries_then_succeeds(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1
    )
    make_train_run(mock_task, data_source, "fail-item")

    attempts = {"n": 0}

    def score_fn(task_run):
        attempts["n"] += 1
        if attempts["n"] == 1:
            # Classified as transient by the eval runner's retry predicate.
            raise ValueError("This task requires a specific output schema")
        return {"accuracy": 0.0}

    result = await run_job(job, eval_config, score_fn, max_retries=2)

    # Retried once then succeeded — the item is judged, no error surfaced.
    assert attempts["n"] == 2
    assert len(result.errors) == 0
    assert len(result.judged_runs) == 1
    assert result.failing_count == 1


@pytest.mark.asyncio
async def test_non_transient_error_not_retried(mock_task, data_source):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1
    )
    make_train_run(mock_task, data_source, "err-item")

    attempts = {"n": 0}

    def score_fn(task_run):
        attempts["n"] += 1
        raise RuntimeError("hard failure")

    result = await run_job(job, eval_config, score_fn, max_retries=2)

    # A non-transient error is collected once, not retried (even with retries enabled).
    assert attempts["n"] == 1
    assert len(result.judged_runs) == 0
    assert len(result.errors) == 1
    assert "hard failure" in result.errors[0].error


def test_default_retry_config(mock_task, data_source):
    # The constructor keeps the historical default (2 retries, 2s base delay) so
    # existing callers are unaffected; background jobs override with a more
    # patient schedule.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1
    )

    runner = JudgeFeedbackBatchRunner(job, eval_config)

    assert runner._max_retries == 2
    assert runner._retry_delay == 2.0


@pytest.mark.asyncio
async def test_transient_retries_back_off_exponentially(mock_task, data_source):
    # Rate-limit-class errors retry with EXPONENTIAL backoff (delay, 2x, ...) — a fixed gap just
    # re-floods a throttled provider, so each retry waits longer.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=1, max_samples=1
    )
    make_train_run(mock_task, data_source, "fail-item")

    attempts = {"n": 0}

    def score_fn(task_run):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            # Classified as transient by the eval runner's retry predicate.
            raise ValueError("This task requires a specific output schema")
        return {"accuracy": 0.0}

    delays: list[float] = []

    async def fake_sleep(d):
        delays.append(d)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.judge_feedback_batch_runner.legacy_eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn, generate=False),
        )
        mp.setattr(
            "kiln_ai.adapters.eval.judge_feedback_batch_runner.asyncio.sleep",
            fake_sleep,
        )
        # Pin the jitter factor so the exponential progression is exact.
        mp.setattr(
            "kiln_ai.utils.async_job_runner.random.uniform",
            lambda a, b: 1.0,
        )
        runner = JudgeFeedbackBatchRunner(
            job, eval_config, rng=random.Random(1), max_retries=2, retry_delay=1.0
        )
        result = await runner.run(concurrency=1)

    # Two transient failures → two retries → backoff of 1*2^0 then 1*2^1.
    assert attempts["n"] == 3
    assert delays == [1.0, 2.0]
    assert len(result.judged_runs) == 1


@pytest.mark.asyncio
async def test_generate_mode_runs_config_and_judges_fresh_output(
    mock_task, data_source
):
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    run_config = make_run_config(mock_task)

    # Tagged val items (should be run through the candidate) + a non-val item (should be ignored).
    val_ids = {
        make_train_run(mock_task, data_source, f"val-{i}", tags=["val"]).id
        for i in range(2)
    }
    make_train_run(mock_task, data_source, "other", tags=["train"])
    runs_before = len(mock_task.runs())

    job = JudgeFeedbackBatch(
        name="gate",
        target_tags=["val"],
        eval_config_id=eval_config.id,
        run_config_id=run_config.id,
        generate_outputs=True,
        stop_after_failures=None,
        max_samples=10,
        parent=mock_task,
    )
    job.save_to_file()

    calls: list[str] = []

    def score_fn(task_run):
        return {"accuracy": 0.0}  # every generated output fails

    result = await run_job(job, eval_config, score_fn, calls=calls)

    # Only the tagged val items were run through the candidate config; full coverage, no early-stop.
    assert set(calls) == val_ids
    assert result.num_judged == 2
    assert {r.task_run_id for r in result.judged_runs} == val_ids
    # Provenance: each judged run records the config that produced the output.
    assert all(r.run_config_id == run_config.id for r in result.judged_runs)
    # The generated outputs are ephemeral — no new dataset TaskRuns were created.
    assert len(mock_task.runs()) == runs_before


@pytest.mark.asyncio
async def test_generate_mode_surfaces_usage(mock_task, data_source):
    # In generate mode the candidate's token/cost/latency must flow through to each run and aggregate.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    run_config = make_run_config(mock_task)

    val_ids = {
        make_train_run(mock_task, data_source, f"val-{i}", tags=["val"]).id
        for i in range(2)
    }

    job = JudgeFeedbackBatch(
        name="gate",
        target_tags=["val"],
        eval_config_id=eval_config.id,
        run_config_id=run_config.id,
        generate_outputs=True,
        stop_after_failures=None,
        max_samples=10,
        parent=mock_task,
    )
    job.save_to_file()

    fresh_usage = Usage(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cost=0.005,
        total_llm_latency_ms=250,
    )
    result = await run_job(
        job, eval_config, lambda _r: {"accuracy": 1.0}, fresh_usage=fresh_usage
    )

    # Each judged run carries the generation's usage, keyed by task_run_id for pairing.
    assert {r.task_run_id for r in result.judged_runs} == val_ids
    assert all(
        r.usage is not None and r.usage.cost == 0.005 for r in result.judged_runs
    )
    # Two items, so the total sums and the means equal the per-item value.
    assert result.total_usage is not None
    assert result.total_usage.cost == pytest.approx(0.01)
    assert result.total_usage.total_tokens == 240
    assert result.mean_cost == pytest.approx(0.005)
    assert result.mean_latency_ms == pytest.approx(250)


@pytest.mark.asyncio
async def test_judge_only_mode_has_no_usage(mock_task, data_source):
    # Judging existing outputs generates nothing — no usage to surface, on runs or aggregates.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    make_train_run(mock_task, data_source, "item", tags=["train"])

    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=10
    )  # target_tags defaults to ["train"], generate_outputs to False

    result = await run_job(job, eval_config, lambda _r: {"accuracy": 1.0})

    assert result.judged_runs and all(r.usage is None for r in result.judged_runs)
    assert result.total_usage is None
    assert result.mean_cost is None
    assert result.mean_latency_ms is None


def test_aggregate_usage_sums_and_means():
    # Sums field-wise across runs that carried usage; means divide only by runs reporting that field.
    runs = [
        JudgeFeedbackBatchRun(
            task_run_id="a",
            scores={"accuracy": 1.0},
            passed=True,
            usage=Usage(cost=0.01, total_llm_latency_ms=100, total_tokens=50),
        ),
        JudgeFeedbackBatchRun(
            task_run_id="b",
            scores={"accuracy": 1.0},
            passed=True,
            usage=Usage(cost=0.03, total_llm_latency_ms=None, total_tokens=70),
        ),
        # A run with no usage (e.g. a cached judge-only result) is ignored by the aggregate.
        JudgeFeedbackBatchRun(task_run_id="c", scores={"accuracy": 1.0}, passed=True),
    ]
    total, mean_cost, mean_latency = aggregate_usage(runs)
    assert total is not None
    assert total.cost == pytest.approx(0.04)
    assert total.total_tokens == 120
    # Two runs reported cost → mean over 2; only one reported latency → mean over 1.
    assert mean_cost == pytest.approx(0.02)
    assert mean_latency == pytest.approx(100)


def test_aggregate_usage_empty_is_none():
    runs = [
        JudgeFeedbackBatchRun(task_run_id="a", scores={"accuracy": 1.0}, passed=True)
    ]
    assert aggregate_usage(runs) == (None, None, None)
    assert aggregate_usage([]) == (None, None, None)


def test_reference_answer_eval_rejected_for_existing_outputs(mock_task):
    # Reference-answer evals need something to compare against; judging an existing output (no
    # generation) has no reference, so the runner rejects the combination up front.
    eval = Eval(
        name="ref",
        eval_set_filter_id="all",
        eval_configs_filter_id="all",
        output_scores=[
            EvalOutputScore(name="Accuracy", type=TaskOutputRatingType.pass_fail)
        ],
        evaluation_data_type=EvalDataType.reference_answer,
        parent=mock_task,
    )
    eval.save_to_file()
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config
    )  # generate_outputs defaults to False

    with pytest.raises(ValueError, match="Reference-answer"):
        JudgeFeedbackBatchRunner(job, eval_config)


@pytest.mark.asyncio
async def test_unexpected_error_does_not_abort_batch(
    mock_task, data_source, monkeypatch
):
    # An unexpected throw in one item's post-judge processing must not discard the rest of the chunk.
    eval = make_eval(mock_task)
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=10
    )
    good = make_train_run(mock_task, data_source, "good")
    boom = make_train_run(mock_task, data_source, "boom")

    real_example_fails = judge_feedback_batch_runner.example_fails

    def flaky_example_fails(scores, output_scores, threshold):
        if scores.get("accuracy") == 0.123:
            raise RuntimeError("kaboom")
        return real_example_fails(scores, output_scores, threshold)

    monkeypatch.setattr(
        judge_feedback_batch_runner, "example_fails", flaky_example_fails
    )

    def score_fn(task_run):
        return {"accuracy": 0.123 if task_run.input == "boom" else 1.0}

    result = await run_job(job, eval_config, score_fn)

    # The good item still succeeded; the throwing item is collected as an error, batch not aborted.
    assert {r.task_run_id for r in result.judged_runs} == {good.id}
    assert len(result.errors) == 1
    assert result.errors[0].task_run_id == boom.id
    assert "kaboom" in result.errors[0].error


@pytest.mark.asyncio
async def test_mean_normalized_scores_are_continuous(mock_task, data_source):
    # The continuous signal the binary pass/fail discards: a five-star eval with items at different
    # stars yields a fractional per-dimension mean, not just a failure count.
    eval = make_eval(
        mock_task, score_type=TaskOutputRatingType.five_star, name="Quality"
    )
    eval_config = make_eval_config(eval)
    job = make_judge_feedback_batch(
        mock_task, eval_config, stop_after_failures=None, max_samples=10
    )
    make_train_run(mock_task, data_source, "a")
    make_train_run(mock_task, data_source, "b")

    stars = {"a": 3.0, "b": 5.0}  # five_star normalizes (s-1)/4 -> 0.5 and 1.0

    def score_fn(task_run):
        return {"quality": stars[task_run.input]}

    result = await run_job(job, eval_config, score_fn)

    assert result.mean_normalized_scores["quality"] == pytest.approx(0.75)
    assert result.mean_normalized_score == pytest.approx(0.75)
