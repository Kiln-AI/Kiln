"""Lazy large fields on the real datamodel classes: what they mark, and that a cached
record still reads, dumps, saves and summarizes exactly like a cache-off load."""

import copy
import json
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, create_model

from kiln_ai.datamodel import Project, Task, TaskOutput, TaskOutputRating, TaskRun
from kiln_ai.datamodel.basemodel import KilnBaseModel, KilnParentedModel
from kiln_ai.datamodel.dataset_filters import (
    HighRatingDatasetFilter,
    ThinkingModelDatasetFilter,
    ThinkingModelHighRatedFilter,
)
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding
from kiln_ai.datamodel.eval import EvalRun
from kiln_ai.datamodel.lazy_fields import (
    LargeField,
    LazyFieldPlan,
    LazyFieldsMixin,
    SummaryValue,
)
from kiln_ai.datamodel.task_output import DataSource, DataSourceType
from kiln_ai.datamodel.world import WorldEpisode, WorldReset
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

LAZY_CLASSES: list[type[LazyFieldsMixin]] = [
    TaskRun,
    TaskOutput,
    WorldEpisode,
    EvalRun,
    ChunkEmbeddings,
]

TRACE: list[ChatCompletionMessageParam] = [
    {"role": "user", "content": "What is the capital of France?"},
    {"role": "assistant", "content": "Paris."},
]


@pytest.fixture
def task(tmp_path) -> Task:
    project = Project(name="Project", path=tmp_path / "project" / "project.kiln")
    project.save_to_file()
    task = Task(name="Task", instruction="Answer the question.", parent=project)
    task.save_to_file()
    return task


def human_source() -> DataSource:
    return DataSource(type=DataSourceType.human, properties={"created_by": "tester"})


def world_episode(final_state: dict[str, Any] | None) -> WorldEpisode:
    return WorldEpisode(
        reset=WorldReset(world_id="world_1", reset_kwargs={"scenario": "easy"}),
        episode_id="episode_1",
        world_version="env@1.0.0",
        final_state=final_state,
    )


def save_task_run(task: Task, **overrides: Any) -> Path:
    """A run with every large field set; `overrides` replaces any of its fields."""
    fields: dict[str, Any] = {
        "input": "The input of the run. " * 20,
        "input_source": human_source(),
        "output": TaskOutput(
            output="The output of the run. " * 20,
            source=human_source(),
            rating=TaskOutputRating(value=5.0),
        ),
        "repair_instructions": "Make it shorter.",
        "repaired_output": TaskOutput(output="Shorter.", source=human_source()),
        "intermediate_outputs": {"reasoning": "Step by step."},
        "trace": copy.deepcopy(TRACE),
        "world_episode": world_episode({"notes": ["visited"]}),
        "tags": ["golden"],
    }
    fields.update(overrides)
    run = TaskRun(parent=task, **fields)
    run.save_to_file()
    assert run.path is not None
    return run.path


def save_eval_run(tmp_path: Path, **overrides: Any) -> Path:
    """A legacy inline eval run, which carries its trace on the record."""
    fields: dict[str, Any] = {
        "dataset_id": "item_1",
        "task_run_config_id": "run_config_1",
        "input": "The input that was scored.",
        "output": "The output that was scored.",
        "reference_answer": "The reference answer.",
        "intermediate_outputs": {"chain_of_thought": "The judge's thinking."},
        "task_run_trace": json.dumps(TRACE),
        "judge_trace": copy.deepcopy(TRACE),
        "scores": {"accuracy": 4.0},
    }
    fields.update(overrides)
    eval_run = EvalRun(path=tmp_path / "eval_run" / "eval_run.kiln", **fields)
    eval_run.save_to_file()
    assert eval_run.path is not None
    return eval_run.path


def save_chunk_embeddings(tmp_path: Path) -> Path:
    embeddings = ChunkEmbeddings(
        path=tmp_path / "chunk_embeddings" / "chunk_embeddings.kiln",
        embedding_config_id="embedding_config_1",
        embeddings=[Embedding(vector=[0.1 * i, 0.2, 0.3]) for i in range(4)],
    )
    embeddings.save_to_file()
    assert embeddings.path is not None
    return embeddings.path


def load_cached(cls: type[KilnBaseModel], path: Path) -> Any:
    return cls.load_from_file(path, readonly=True)


def load_uncached(cls: type[KilnBaseModel], path: Path) -> Any:
    """The record as a readonly load with the cache off returns it."""
    record = cls._validate_file_data(
        json.loads(path.read_text(encoding="utf-8")), path, None
    )
    record.mark_as_readonly()
    return record


def value_at(record: BaseModel, value_path: tuple[str, ...]) -> Any:
    value: Any = record
    for name in value_path:
        value = getattr(value, name)
    return value


def test_plans_for_marked_classes():
    expected = {
        TaskRun: {
            ("input",),
            ("trace",),
            ("intermediate_outputs",),
            ("output", "output"),
            ("repaired_output", "output"),
            ("world_episode", "final_state"),
        },
        TaskOutput: {("output",)},
        WorldEpisode: {("final_state",)},
        EvalRun: {
            ("input",),
            ("output",),
            ("task_run_trace",),
            ("judge_trace",),
            ("intermediate_outputs",),
            ("reference_answer",),
        },
        ChunkEmbeddings: {("embeddings",)},
    }

    assert {
        cls: set(LazyFieldPlan.for_class(cls).paths) for cls in LAZY_CLASSES
    } == expected


@pytest.mark.parametrize(
    "save_record",
    [
        lambda task, tmp_path: (TaskRun, save_task_run(task)),
        lambda task, tmp_path: (EvalRun, save_eval_run(tmp_path)),
        lambda task, tmp_path: (ChunkEmbeddings, save_chunk_embeddings(tmp_path)),
    ],
    ids=["task_run", "eval_run", "chunk_embeddings"],
)
def test_round_trip_through_cache_eviction_and_restore(
    save_record: Callable[[Task, Path], tuple[type[KilnBaseModel], Path]],
    task,
    tmp_path,
    model_cache_enabled,
    evict_large_values,
    large_field_restores,
):
    cls, path = save_record(task, tmp_path)
    uncached = load_uncached(cls, path)
    record = load_cached(cls, path)
    assert record.has_unloaded_fields()
    assert model_cache_enabled.stats().records_with_large_values == 1

    evict_large_values()

    for value_path in LazyFieldPlan.for_class(cls).paths:
        assert value_path[-1] not in value_at(record, value_path[:-1]).__dict__
        assert value_at(record, value_path) == value_at(uncached, value_path)
        assert value_at(record, value_path) is not None
    assert record.model_dump() == uncached.model_dump()
    assert record.model_dump_json() == uncached.model_dump_json()
    assert record == uncached
    assert record.mutable_copy().model_dump() == uncached.model_dump()
    assert large_field_restores.call_count == 1


def test_task_run_detach_scrubs_validated_values(task, model_cache_enabled):
    run = load_cached(TaskRun, save_task_run(task))

    assert "_last_validated_input" not in run.__dict__
    assert "_last_validated_output" not in run.__dict__
    assert run._last_validated_input == run.input


def test_save_evicted_run_changes_only_the_edit(
    task, model_cache_enabled, evict_large_values
):
    path = save_task_run(task)
    original = json.loads(path.read_text(encoding="utf-8"))
    run = load_cached(TaskRun, path)
    evict_large_values()

    editable = run.mutable_copy()
    editable.tags = ["golden", "reviewed"]
    editable.save_to_file()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {**original, "tags": ["golden", "reviewed"]}
    assert list(saved) == list(original)


def test_task_run_summary_values():
    run = TaskRun(
        input="i" * 101,
        output=TaskOutput(output="o" * 100),
        trace=copy.deepcopy(TRACE),
        intermediate_outputs={"chain_of_thought": "thinking"},
    )

    assert run.input_preview == "i" * 100 + "…"
    assert run.output_preview == "o" * 100
    assert run.trace_length == 2
    assert run.has_thinking
    assert run.has_thinking_training_data()

    empty = TaskRun(input="", output=TaskOutput(output=""))
    assert empty.input_preview == ""
    assert empty.output_preview is None
    assert empty.trace_length == 0
    assert not empty.has_thinking


SUMMARY_CASES: list[dict[str, Any]] = [
    {"input": "", "output": TaskOutput(output="")},
    {"input": "short", "output": TaskOutput(output="short")},
    {"input": "x" * 100, "output": TaskOutput(output="y" * 100)},
    {"input": "x" * 250, "output": TaskOutput(output="y" * 250)},
    {"trace": None},
    {"trace": []},
    {"intermediate_outputs": None},
    {"intermediate_outputs": {"reasoning": "r"}},
    {"intermediate_outputs": {"chain_of_thought": "c"}},
    {"intermediate_outputs": {"reasoning": "", "chain_of_thought": "c"}},
    {"intermediate_outputs": {"other_step": "o"}},
    {"world_episode": None},
    {"world_episode": world_episode(None)},
]


@pytest.mark.parametrize("overrides", SUMMARY_CASES)
def test_task_run_summary_values_match_live_values(
    overrides, task, model_cache_enabled, evict_large_values, large_field_restores
):
    path = save_task_run(task, **copy.deepcopy(overrides))
    uncached = load_uncached(TaskRun, path)
    run = load_cached(TaskRun, path)
    evict_large_values()

    assert run.input_preview == uncached.input_preview
    assert run.output_preview == uncached.output_preview
    assert run.trace_length == uncached.trace_length
    assert run.has_thinking == uncached.has_thinking
    assert run.has_thinking_training_data() == uncached.has_thinking_training_data()
    if uncached.world_episode is not None:
        assert (
            run.world_episode.has_final_state == uncached.world_episode.has_final_state
        )
    large_field_restores.assert_not_called()


@pytest.mark.parametrize(
    "judge_trace, length", [(None, 0), ([], 0), (TRACE + TRACE[:1], 3)]
)
def test_eval_run_judge_trace_length(
    judge_trace,
    length,
    tmp_path,
    model_cache_enabled,
    evict_large_values,
    large_field_restores,
):
    path = save_eval_run(tmp_path, judge_trace=copy.deepcopy(judge_trace))
    eval_run = load_cached(EvalRun, path)
    evict_large_values()

    assert eval_run.judge_trace_length == length
    assert load_uncached(EvalRun, path).judge_trace_length == length
    large_field_restores.assert_not_called()


def summary_names(cls: type[BaseModel]) -> set[str]:
    return {
        name
        for klass in cls.__mro__
        for name, attr in vars(klass).items()
        if isinstance(attr, SummaryValue)
    }


def test_summary_values_not_serialized(task, tmp_path, model_cache_enabled):
    run = load_cached(TaskRun, save_task_run(task))
    eval_run = load_cached(EvalRun, save_eval_run(tmp_path))
    names = (
        summary_names(TaskRun) | summary_names(EvalRun) | summary_names(WorldEpisode)
    )
    assert names == {
        "input_preview",
        "output_preview",
        "trace_length",
        "has_thinking",
        "judge_trace_length",
        "has_final_state",
    }

    run_dump = run.model_dump()
    assert names.isdisjoint(run_dump)
    assert names.isdisjoint(run_dump["world_episode"])
    assert names.isdisjoint(eval_run.model_dump())
    for cls in LAZY_CLASSES:
        for mode in ("validation", "serialization"):
            schema = json.dumps(cls.model_json_schema(mode=mode))
            assert not any(f'"{name}"' in schema for name in names)


def plain_twin(cls: type[BaseModel], twins: dict[type, type[BaseModel]]) -> type:
    """A copy of a lazy class without the mixin or markers, from the same fields.

    Nested lazy classes are swapped for their own twins. Validators and methods aren't
    copied: they don't shape the JSON schema.
    """
    if cls in twins:
        return twins[cls]
    base = next(
        klass
        for klass in cls.__mro__[1:]
        if klass in (KilnParentedModel, KilnBaseModel, BaseModel)
    )
    fields: dict[str, Any] = {}
    for name, info in cls.model_fields.items():
        if name in base.model_fields:
            continue
        twin_info = copy.copy(info)
        twin_info.metadata = [m for m in info.metadata if not isinstance(m, LargeField)]
        fields[name] = (twin_annotation(info.annotation, twins), twin_info)
    twin = create_model(cls.__name__, __base__=base, __doc__=cls.__doc__, **fields)
    twins[cls] = twin
    return twin


def twin_annotation(annotation: Any, twins: dict[type, type[BaseModel]]) -> Any:
    if isinstance(annotation, type) and issubclass(annotation, LazyFieldsMixin):
        return plain_twin(annotation, twins)
    if get_origin(annotation) in (Union, types.UnionType):
        return Union[tuple(twin_annotation(arg, twins) for arg in get_args(annotation))]
    return annotation


@pytest.mark.parametrize("cls", LAZY_CLASSES, ids=lambda cls: cls.__name__)
@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_serialization_schema_unchanged(cls, mode):
    twin = plain_twin(cls, {})

    assert not issubclass(twin, LazyFieldsMixin)
    assert cls.model_json_schema(mode=mode) == twin.model_json_schema(mode=mode)


def test_dataset_filters_read_no_large_fields(
    task, model_cache_enabled, evict_large_values, large_field_restores
):
    thinking_path = save_task_run(task)
    plain_path = save_task_run(
        task,
        intermediate_outputs=None,
        repair_instructions=None,
        repaired_output=None,
    )
    runs = [load_cached(TaskRun, path) for path in (thinking_path, plain_path)]
    evict_large_values()

    assert [ThinkingModelDatasetFilter(run) for run in runs] == [True, False]
    assert [ThinkingModelHighRatedFilter(run) for run in runs] == [True, False]
    assert [HighRatingDatasetFilter(run) for run in runs] == [True, True]
    large_field_restores.assert_not_called()
