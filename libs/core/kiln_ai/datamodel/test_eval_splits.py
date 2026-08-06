import pytest

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
    EvalInput,
    EvalInputSplit,
    EvalOutputScore,
    EvalRun,
    SingleTurnEvalInputData,
    TaskRunSplit,
    UserMessage,
)
from kiln_ai.datamodel.eval_splits import (
    ResolvedSplit,
    eval_run_item_key,
    resolve_split,
)


@pytest.fixture
def task(tmp_path):
    task = Task(
        name="Test Task", instruction="do the thing", path=tmp_path / "task.kiln"
    )
    task.save_to_file()
    return task


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


def make_task_run(task: Task, data_source: DataSource, tags: list[str]) -> TaskRun:
    task_run = TaskRun(
        parent=task,
        input="in",
        input_source=data_source,
        output=TaskOutput(output="out"),
        tags=tags,
    )
    task_run.save_to_file()
    return task_run


def make_eval_input(task: Task, tags: list[str]) -> EvalInput:
    eval_input = EvalInput(
        parent=task,
        data=SingleTurnEvalInputData(user_message=UserMessage(text="in")),
        tags=tags,
    )
    eval_input.save_to_file()
    return eval_input


def make_eval(task: Task, **kwargs) -> Eval:
    eval = Eval(
        name="Test Eval",
        parent=task,
        output_scores=[
            EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
        ],
        **kwargs,
    )
    eval.save_to_file()
    return eval


def test_resolve_task_run_backed_split(task, data_source):
    wanted = make_task_run(task, data_source, ["train_x"])
    make_task_run(task, data_source, ["test_x"])
    make_eval_input(task, ["train_x"])
    eval = make_eval(
        task,
        splits={
            "test": TaskRunSplit(filter_id="tag::test_x"),
            "train": TaskRunSplit(filter_id="tag::train_x"),
        },
    )

    resolved = resolve_split(task, eval, "train")

    assert resolved is not None
    assert resolved.source == "task_run"
    assert len(resolved) == 1
    assert [item.id for item in resolved.items] == [wanted.id]
    assert resolved.item_keys() == {("task_run", wanted.id)}


def test_resolve_eval_input_backed_split(task, data_source):
    wanted = make_eval_input(task, ["val_x"])
    make_eval_input(task, ["other"])
    make_task_run(task, data_source, ["val_x"])
    eval = make_eval(
        task,
        splits={
            "test": TaskRunSplit(filter_id="tag::test_x"),
            "val": EvalInputSplit(filter_id="tag::val_x"),
        },
    )

    resolved = resolve_split(task, eval, "val")

    assert resolved is not None
    assert resolved.source == "eval_input"
    assert [item.id for item in resolved.items] == [wanted.id]
    assert resolved.item_keys() == {("eval_input", wanted.id)}


@pytest.mark.parametrize(
    "split_ref",
    [TaskRunSplit(filter_id="tag::nothing"), EvalInputSplit(filter_id="tag::nothing")],
)
def test_configured_split_matching_nothing_is_empty_not_none(
    task, data_source, split_ref
):
    """Empty and absent are different answers; only absent is None."""
    make_task_run(task, data_source, ["something"])
    make_eval_input(task, ["something"])
    eval = make_eval(task, splits={"test": split_ref})

    resolved = resolve_split(task, eval, "test")

    assert resolved is not None
    assert len(resolved) == 0
    assert resolved.item_keys() == set()


@pytest.mark.parametrize("split", ["train", "val"])
def test_absent_split_resolves_to_none(task, split):
    eval = make_eval(task, splits={"test": TaskRunSplit(filter_id="tag::test_x")})
    assert resolve_split(task, eval, split) is None


def test_legacy_eval_resolves_its_test_split(task, data_source):
    """No caller has to know the split came from eval_set_filter_id."""
    wanted = make_task_run(task, data_source, ["test_x"])
    eval = make_eval(task, eval_set_filter_id="tag::test_x")

    resolved = resolve_split(task, eval, "test")

    assert resolved is not None
    assert [item.id for item in resolved.items] == [wanted.id]


def test_eval_run_item_key_for_both_shapes():
    task_run_scored = EvalRun(
        dataset_id="1234",
        task_run_config_id="rc",
        input="in",
        output="out",
        scores={"score": 1.0},
    )
    eval_input_scored = EvalRun(
        eval_input_id="1234",
        task_run_config_id="rc",
        input="in",
        output="out",
        scores={"score": 1.0},
    )

    assert eval_run_item_key(task_run_scored) == ("task_run", "1234")
    assert eval_run_item_key(eval_input_scored) == ("eval_input", "1234")


def test_eval_run_item_key_requires_an_item():
    unvalidated = EvalRun.model_construct(dataset_id=None, eval_input_id=None)
    with pytest.raises(ValueError, match="neither a dataset_id nor an eval_input_id"):
        eval_run_item_key(unvalidated)


def test_membership_does_not_cross_stores(task, data_source):
    """Ids are 12 digits from one generator shared by every model type, so a bare-id
    membership test can admit one store's result into the other store's split."""
    shared_id = "999999999999"
    task_run = TaskRun(
        id=shared_id,
        parent=task,
        input="in",
        input_source=data_source,
        output=TaskOutput(output="out"),
        tags=["val_x"],
    )
    task_run.save_to_file()
    eval_input = EvalInput(
        id=shared_id,
        parent=task,
        data=SingleTurnEvalInputData(user_message=UserMessage(text="in")),
        tags=["val_x"],
    )
    eval_input.save_to_file()

    eval = make_eval(
        task,
        splits={
            "test": TaskRunSplit(filter_id="tag::test_x"),
            "val": EvalInputSplit(filter_id="tag::val_x"),
        },
    )
    eval_input_backed_val = resolve_split(task, eval, "val")
    assert eval_input_backed_val is not None

    task_run_result = EvalRun(
        dataset_id=shared_id,
        task_run_config_id="rc",
        input="in",
        output="out",
        scores={"score": 1.0},
    )
    eval_input_result = EvalRun(
        eval_input_id=shared_id,
        task_run_config_id="rc",
        input="in",
        output="out",
        scores={"score": 1.0},
    )

    assert eval_run_item_key(task_run_result) not in eval_input_backed_val
    assert eval_run_item_key(eval_input_result) in eval_input_backed_val


def test_resolved_split_len_and_contains(task, data_source):
    runs = [make_task_run(task, data_source, ["test_x"]) for _ in range(3)]
    split = ResolvedSplit(name="test", source="task_run", items=runs, eval_id="e1")

    assert len(split) == 3
    assert ("task_run", runs[0].id) in split
    assert ("eval_input", runs[0].id) not in split


def test_item_keys_returns_a_copy(task, data_source):
    run = make_task_run(task, data_source, ["test_x"])
    split = ResolvedSplit(name="test", source="task_run", items=[run], eval_id="e1")

    keys = split.item_keys()
    keys.clear()

    assert split.item_keys() == {("task_run", run.id)}


def test_golden_set_is_not_a_split(task, data_source):
    """Golden stays outside the splits dict, so resolve_split can't reach its items."""
    make_task_run(task, data_source, ["golden_x"])
    eval = make_eval(
        task,
        splits={"test": TaskRunSplit(filter_id="tag::test_x")},
        eval_configs_filter_id="tag::golden_x",
    )

    assert "golden" not in eval.splits
    resolved = resolve_split(task, eval, "test")
    assert resolved is not None
    assert len(resolved) == 0
