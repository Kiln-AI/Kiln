import random
from typing import Callable, Dict

import pytest

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.failing_examples import (
    example_fails,
    feedback_from_intermediate_outputs,
    find_failing_train_examples,
    score_passes,
)
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
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
    EvalRun,
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
        description="test",
        instruction="do the thing",
        path=tmp_path / "task.kiln",
    )
    task.save_to_file()
    return task


@pytest.fixture
def mock_eval(mock_task):
    eval = Eval(
        name="test",
        description="test",
        eval_set_filter_id="all",
        eval_configs_filter_id="all",
        train_set_filter_id="tag::train",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Check if the output is accurate",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        parent=mock_task,
    )
    eval.save_to_file()
    return eval


@pytest.fixture
def mock_eval_config(mock_eval):
    eval_config = EvalConfig(
        name="test",
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        parent=mock_eval,
        properties={"eval_steps": ["step1", "step2"]},
    )
    eval_config.save_to_file()
    return eval_config


def make_train_run(task, data_source, input_text: str, tag: str = "train") -> TaskRun:
    run = TaskRun(
        parent=task,
        input=input_text,
        input_source=data_source,
        output=TaskOutput(output=f"output for {input_text}"),
        tags=[tag],
    )
    run.save_to_file()
    return run


def scripted_evaluator_factory(
    score_fn: Callable[[TaskRun], EvalScores],
    calls: list[str] | None = None,
    feedback: Dict[str, str] | None = None,
):
    """Build a patched eval_adapter_from_type that returns a BaseEval scoring via score_fn."""

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


# ---- Pure helper tests ----


def test_score_passes_rating_types():
    # five_star: >= 4 (normalized 0.75) passes the default bar
    assert score_passes(4.0, TaskOutputRatingType.five_star, 0.75) is True
    assert score_passes(3.0, TaskOutputRatingType.five_star, 0.75) is False
    # pass_fail
    assert score_passes(1.0, TaskOutputRatingType.pass_fail, 0.75) is True
    assert score_passes(0.0, TaskOutputRatingType.pass_fail, 0.75) is False
    # pass_fail_critical: 0.0 -> normalized 0.5 -> fails the 0.75 bar
    assert score_passes(1.0, TaskOutputRatingType.pass_fail_critical, 0.75) is True
    assert score_passes(0.0, TaskOutputRatingType.pass_fail_critical, 0.75) is False
    assert score_passes(-1.0, TaskOutputRatingType.pass_fail_critical, 0.75) is False


def test_example_fails_requires_all_scores_below_bar():
    output_scores = [
        EvalOutputScore(name="Accuracy", type=TaskOutputRatingType.pass_fail),
        EvalOutputScore(name="Quality", type=TaskOutputRatingType.five_star),
    ]
    # Both below bar -> fails
    assert example_fails({"accuracy": 0.0, "quality": 2.0}, output_scores, 0.75) is True
    # One passes -> not a failure (ALL must fail)
    assert (
        example_fails({"accuracy": 1.0, "quality": 2.0}, output_scores, 0.75) is False
    )
    assert (
        example_fails({"accuracy": 0.0, "quality": 5.0}, output_scores, 0.75) is False
    )


def test_example_fails_no_relevant_scores():
    assert example_fails({}, [], 0.75) is False


def test_example_fails_with_missing_scores():
    output_scores = [
        EvalOutputScore(name="Accuracy", type=TaskOutputRatingType.pass_fail),
        EvalOutputScore(name="Quality", type=TaskOutputRatingType.five_star),
    ]
    # Quality missing, Accuracy fails -> no present score passes -> example fails
    assert example_fails({"accuracy": 0.0}, output_scores, 0.75) is True
    # Quality missing, Accuracy passes -> a score passes -> not a failure
    assert example_fails({"accuracy": 1.0}, output_scores, 0.75) is False


def test_feedback_from_intermediate_outputs():
    assert feedback_from_intermediate_outputs(None) is None
    assert feedback_from_intermediate_outputs({}) is None
    assert feedback_from_intermediate_outputs({"reasoning": "  because  "}) == "because"
    # prefers reasoning over chain_of_thought
    assert (
        feedback_from_intermediate_outputs(
            {"chain_of_thought": "cot", "reasoning": "r"}
        )
        == "r"
    )
    # falls back to joining other keys
    assert feedback_from_intermediate_outputs({"other": "x"}) == "other: x"


# ---- Orchestration tests ----


@pytest.mark.asyncio
async def test_returns_only_failing_examples(
    mock_task, mock_eval, mock_eval_config, data_source
):
    fail_ids = set()
    for i in range(3):
        fail_ids.add(make_train_run(mock_task, data_source, f"fail-{i}").id)
    for i in range(3):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0 if task_run.input.startswith("fail") else 1.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        result = await find_failing_train_examples(
            mock_eval_config,
            count=2,
            max_samples=6,
            rng=random.Random(42),
        )

    assert len(result.examples) == 2
    assert result.train_set_size == 6
    assert result.hit_cap is False
    for example in result.examples:
        assert example.dataset_id in fail_ids
        assert example.scores == {"accuracy": 0.0}
        assert example.feedback is not None


@pytest.mark.asyncio
async def test_early_stop_limits_num_judged(
    mock_task, mock_eval, mock_eval_config, data_source
):
    for i in range(10):
        make_train_run(mock_task, data_source, f"fail-{i}")

    def score_fn(task_run):
        return {"accuracy": 0.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        # concurrency=1 so we judge one item per chunk and can stop exactly at count
        result = await find_failing_train_examples(
            mock_eval_config,
            count=2,
            max_samples=10,
            concurrency=1,
            rng=random.Random(0),
        )

    assert len(result.examples) == 2
    assert result.num_judged == 2
    assert result.hit_cap is False


@pytest.mark.asyncio
async def test_hit_cap_when_failures_sparse(
    mock_task, mock_eval, mock_eval_config, data_source
):
    # 5 train items, all passing, max_samples == 5 -> cap reached with no failures
    for i in range(5):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 1.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        result = await find_failing_train_examples(
            mock_eval_config,
            count=2,
            max_samples=5,
            rng=random.Random(1),
        )

    assert result.examples == []
    assert result.num_judged == 5
    assert result.hit_cap is True


@pytest.mark.asyncio
async def test_exhausted_train_set_is_not_hit_cap(
    mock_task, mock_eval, mock_eval_config, data_source
):
    # Train set smaller than max_samples and no failures -> exhausted, not capped
    for i in range(3):
        make_train_run(mock_task, data_source, f"pass-{i}")

    def score_fn(task_run):
        return {"accuracy": 1.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        result = await find_failing_train_examples(
            mock_eval_config,
            count=2,
            max_samples=10,
            rng=random.Random(1),
        )

    assert result.examples == []
    assert result.num_judged == 3
    assert result.hit_cap is False


@pytest.mark.asyncio
async def test_persists_eval_run(mock_task, mock_eval, mock_eval_config, data_source):
    run = make_train_run(mock_task, data_source, "fail-0")

    def score_fn(task_run):
        return {"accuracy": 0.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        result = await find_failing_train_examples(
            mock_eval_config, count=1, max_samples=1, rng=random.Random(1)
        )

    assert len(result.examples) == 1
    saved_runs = mock_eval_config.runs()
    assert len(saved_runs) == 1
    saved = saved_runs[0]
    assert saved.dataset_id == run.id
    assert saved.eval_config_eval is True
    assert saved.task_run_config_id is None
    assert saved.scores == {"accuracy": 0.0}


@pytest.mark.asyncio
async def test_reuse_cached_skips_judging(
    mock_task, mock_eval, mock_eval_config, data_source
):
    run = make_train_run(mock_task, data_source, "fail-0")
    # Pre-seed a judged EvalRun for this item
    EvalRun(
        parent=mock_eval_config,
        task_run_config_id=None,
        dataset_id=run.id,
        eval_config_eval=True,
        scores={"accuracy": 0.0},
        input=run.input,
        output=run.output.output,
        intermediate_outputs={"reasoning": "cached feedback"},
    ).save_to_file()

    calls: list[str] = []

    def score_fn(task_run):
        return {"accuracy": 0.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn, calls=calls),
        )
        result = await find_failing_train_examples(
            mock_eval_config, count=1, max_samples=1, rng=random.Random(1)
        )

    assert len(result.examples) == 1
    assert result.examples[0].feedback == "cached feedback"
    # The judge was never invoked, and no new EvalRun was written
    assert calls == []
    assert len(mock_eval_config.runs()) == 1


@pytest.mark.asyncio
async def test_threshold_override_five_star(
    mock_task, mock_eval, mock_eval_config, data_source
):
    mock_eval.output_scores = [
        EvalOutputScore(name="Quality", type=TaskOutputRatingType.five_star)
    ]
    mock_eval.save_to_file()
    make_train_run(mock_task, data_source, "item-0")

    def score_fn(task_run):
        return {"quality": 4.0}  # normalized 0.75

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        # Default bar 0.75: 0.75 >= 0.75 -> passes -> no failures
        passing = await find_failing_train_examples(
            mock_eval_config,
            count=1,
            max_samples=1,
            threshold=0.75,
            rng=random.Random(1),
        )
        # Stricter bar 0.9: 0.75 < 0.9 -> fails. reuse_cached=False so we re-judge.
        failing = await find_failing_train_examples(
            mock_eval_config,
            count=1,
            max_samples=1,
            threshold=0.9,
            reuse_cached=False,
            rng=random.Random(1),
        )

    assert passing.examples == []
    assert len(failing.examples) == 1


@pytest.mark.asyncio
async def test_missing_train_set_raises(mock_eval_config, mock_eval):
    mock_eval.train_set_filter_id = None
    with pytest.raises(ValueError, match="train set filter"):
        await find_failing_train_examples(mock_eval_config, count=1, max_samples=1)


@pytest.mark.asyncio
async def test_count_validation(mock_eval_config):
    with pytest.raises(ValueError, match="count must be"):
        await find_failing_train_examples(mock_eval_config, count=0, max_samples=5)
    with pytest.raises(ValueError, match="max_samples must be"):
        await find_failing_train_examples(mock_eval_config, count=5, max_samples=2)


@pytest.mark.asyncio
async def test_judge_errors_are_skipped(
    mock_task, mock_eval, mock_eval_config, data_source
):
    make_train_run(mock_task, data_source, "error-item")
    fail_run = make_train_run(mock_task, data_source, "fail-item")

    def score_fn(task_run):
        if task_run.input == "error-item":
            raise RuntimeError("Judge error")
        return {"accuracy": 0.0}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "kiln_ai.adapters.eval.failing_examples.eval_adapter_from_type",
            lambda _type: scripted_evaluator_factory(score_fn),
        )
        result = await find_failing_train_examples(
            mock_eval_config, count=2, max_samples=2, rng=random.Random(1)
        )

    # The errored item is skipped (but still counted as examined); only the failure is returned.
    assert len(result.examples) == 1
    assert result.num_judged == 2
    assert result.examples[0].dataset_id == fail_run.id
