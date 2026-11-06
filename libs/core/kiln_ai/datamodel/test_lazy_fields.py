import gc
import importlib
import json
import pickle
import pkgutil
import random
import sys
import threading
import time
import tracemalloc
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    TypeAdapter,
    ValidationError,
    create_model,
    model_serializer,
    model_validator,
)
from pydantic_core import PydanticSerializationError
from typing_extensions import Self

import kiln_ai.datamodel as datamodel_package
from kiln_ai.datamodel import lazy_fields
from kiln_ai.datamodel.basemodel import (
    KilnAttachmentModel,
    KilnBaseModel,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.lazy_fields import (
    LargeField,
    LargeFieldUnavailableError,
    LazyFieldPlan,
    LazyFieldsMixin,
    approx_value_size,
    declares_large_field,
    summary_value,
)
from kiln_ai.datamodel.model_cache import ModelCache
from kiln_ai.utils.open_ai_types import (
    ChatCompletionMessageParam,
    materialize_lazy_content,
)


class LazyOutput(LazyFieldsMixin, KilnBaseModel):
    output: Annotated[str, LargeField()] = Field(description="The output text.")
    rating: int | None = None

    @summary_value
    def output_length(self) -> int:
        return len(self.output)


class LazyRecord(LazyFieldsMixin, KilnParentedModel):
    name: str
    body: Annotated[str, LargeField()]
    notes: Annotated[dict[str, str] | None, LargeField()] = None
    trace: Annotated[list[ChatCompletionMessageParam] | None, LargeField()] = None
    output: LazyOutput
    repaired_output: LazyOutput | None = None
    attachment: KilnAttachmentModel | None = None

    _validated_output: str | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def remember_validated_values(self) -> Self:
        # TaskRun keeps its validated input under an undeclared name, which pydantic
        # stores in __dict__; the declared private attr lives in __pydantic_private__.
        self._last_validated_body = self.body
        self._validated_output = self.output.output
        return self

    @model_validator(mode="after")
    def materialize_trace_content(self) -> Self:
        if self.trace is not None:
            materialize_lazy_content(self.trace)
        return self

    @summary_value
    def body_preview(self) -> str:
        return self.body[:10]

    @summary_value
    def trace_length(self) -> int:
        return len(self.trace) if self.trace else 0

    @summary_value
    def output_preview(self) -> str:
        return self.output.output[:10]


class LazyParent(KilnParentModel, parent_of={"records": LazyRecord}):
    pass


BODY = "The body of the record. " * 20
OUTPUT = "The output of the record."
NOTES = {"source": "test"}
TRACE: list[ChatCompletionMessageParam] = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"},
]


@pytest.fixture
def parent(tmp_path) -> LazyParent:
    parent = LazyParent(path=tmp_path / "lazy_parent.kiln")
    parent.save_to_file()
    return parent


def save_record(
    parent: LazyParent,
    *,
    name: str = "first",
    body: str = BODY,
    notes: dict[str, str] | None = NOTES,
    trace: list[ChatCompletionMessageParam] | None = TRACE,
    output: str = OUTPUT,
    repaired_output: LazyOutput | None = None,
    attachment: KilnAttachmentModel | None = None,
) -> Path:
    record = LazyRecord(
        parent=parent,
        name=name,
        body=body,
        notes=notes,
        trace=deepcopy(trace),
        output=LazyOutput(output=output),
        repaired_output=repaired_output,
        attachment=attachment,
    )
    record.save_to_file()
    assert record.path is not None
    return record.path


@pytest.fixture
def record_path(parent) -> Path:
    return save_record(parent)


def load_cached(path: Path) -> LazyRecord:
    return LazyRecord.load_from_file(path, readonly=True)


def load_uncached(path: Path) -> LazyRecord:
    """The record as a readonly load with the cache off returns it."""
    record = LazyRecord._validate_file_data(
        json.loads(path.read_text(encoding="utf-8")), path, None
    )
    record.mark_as_readonly()
    return record


@pytest.fixture
def cached(record_path, model_cache_enabled) -> LazyRecord:
    return load_cached(record_path)


def evict_large_values(cache: ModelCache) -> None:
    """Drop every entry's large values, keeping the records, as memory pressure does."""
    with cache._lock:
        for path in list(cache._loaded):
            cache._drop_large_values(path)


@pytest.fixture
def evicted(cached, model_cache_enabled) -> LazyRecord:
    evict_large_values(model_cache_enabled)
    return cached


@pytest.fixture
def restores() -> Iterator[MagicMock]:
    """Counts the times a detached record re-reads its file."""
    with patch.object(lazy_fields, "_restore", wraps=lazy_fields._restore) as spy:
        yield spy


def rewrite(path: Path, **changes: Any) -> None:
    """Change the file the way another program would."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def test_plan_finds_top_level_and_nested_paths():
    assert LazyFieldPlan.for_class(LazyRecord).paths == (
        ("body",),
        ("notes",),
        ("trace",),
        ("output", "output"),
        ("repaired_output", "output"),
    )
    assert LazyFieldPlan.for_class(LazyOutput).paths == (("output",),)


@pytest.mark.parametrize(
    "annotation",
    [
        list[Annotated[str, LargeField()]],
        dict[str, Annotated[str, LargeField()]],
        list[LazyOutput],
        LazyOutput | str,
    ],
    ids=[
        "marker_in_list",
        "marker_in_dict",
        "lazy_model_in_list",
        "lazy_model_in_union",
    ],
)
def test_plan_rejects_hidden_large_fields(annotation):
    with pytest.raises(TypeError, match="Mark the container field itself"):
        create_model(
            "HiddenLargeField",
            __base__=(LazyFieldsMixin, KilnBaseModel),
            items=(annotation, ...),
        )


@pytest.mark.parametrize(
    "annotation",
    [Annotated[str, LargeField()], list[Annotated[str, LargeField()]]],
    ids=["field", "inside_list"],
)
def test_marker_requires_mixin(annotation):
    with pytest.raises(TypeError, match="must inherit LazyFieldsMixin"):
        create_model("NotLazy", __base__=KilnBaseModel, body=(annotation, ...))


def datamodel_model_classes() -> list[type[BaseModel]]:
    classes: list[type[BaseModel]] = []
    for module_info in pkgutil.walk_packages(
        datamodel_package.__path__, f"{datamodel_package.__name__}."
    ):
        if module_info.name.rsplit(".", 1)[-1].startswith("test_"):
            continue
        module = importlib.import_module(module_info.name)
        classes.extend(
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, BaseModel)
            and value.__module__ == module.__name__
        )
    return classes


def test_all_datamodel_markers_have_mixin():
    """Plain BaseModel classes aren't checked at import, unlike KilnBaseModel ones."""
    classes = datamodel_model_classes()
    assert len(classes) > 50

    assert [
        cls.__qualname__
        for cls in classes
        if declares_large_field(cls) and not issubclass(cls, LazyFieldsMixin)
    ] == []
    assert declares_large_field(LazyRecord)
    assert not declares_large_field(LazyParent)


def test_custom_model_serializer_rejected():
    with pytest.raises(TypeError, match="defines a model_serializer"):

        class CustomSerializer(LazyFieldsMixin, KilnBaseModel):
            body: Annotated[str, LargeField()]

            @model_serializer(mode="plain")
            def dump_body(self) -> dict[str, str]:
                return {"body": self.body}

    with pytest.raises(TypeError, match="defines a model_serializer"):

        class ReplacedSerializer(LazyFieldsMixin, KilnBaseModel):
            body: Annotated[str, LargeField()]

            @model_serializer(mode="plain")
            def _serialize_with_large_fields(self) -> dict[str, str]:
                return {"body": self.body}


def test_cache_off_load_has_no_lazy_state(record_path):
    in_memory = LazyRecord(name="x", body=BODY, output=LazyOutput(output=OUTPUT))

    for record in (load_cached(record_path), in_memory):
        assert record._lazy is None
        assert record.output._lazy is None
        assert "body" in record.__dict__
        assert "output" in record.output.__dict__
        assert not record.has_unloaded_fields()
    assert ModelCache.shared().stats().records == 0


def test_cache_on_load_detaches_large_values(cached, model_cache_enabled):
    assert cached._lazy is not None
    assert {"body", "notes", "trace"}.isdisjoint(cached.__dict__)
    assert "output" not in cached.output.__dict__
    assert cached.has_unloaded_fields()
    assert model_cache_enabled.stats().records_with_large_values == 1
    assert load_cached(cached.path) is cached


def test_detach_removes_values_and_keeps_real_none(
    parent, model_cache_enabled, restores
):
    record = load_cached(save_record(parent, notes=None))

    with patch.object(
        model_cache_enabled,
        "large_values_for",
        wraps=model_cache_enabled.large_values_for,
    ) as large_values_for:
        assert record.__dict__["notes"] is None
        assert record.notes is None
        assert record.repaired_output is None
        large_values_for.assert_not_called()
    assert "trace" not in record.__dict__
    assert record._lazy is not None
    assert record._lazy.missing == {"body", "trace"}
    restores.assert_not_called()


def test_detach_scrubs_private_references(parent, model_cache_enabled):
    big_body = "b" * 2_000_000
    big_output = "o" * 2_000_000
    path = save_record(parent, body=big_body, output=big_output)
    tracemalloc.start()
    try:
        record = load_cached(path)
        assert "_last_validated_body" not in record.__dict__
        assert "_validated_output" not in (record.__pydantic_private__ or {})
        # Still readable: they resolve like the fields they pointed to.
        assert record._last_validated_body == big_body
        assert record._validated_output == big_output
        gc.collect()
        with_values = tracemalloc.get_traced_memory()[0]

        model_cache_enabled.clear()
        gc.collect()
        without_values = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()

    assert with_values - without_values > 0.9 * (len(big_body) + len(big_output))


def test_read_missing_field_uses_store(cached, restores):
    assert cached.body == BODY
    assert cached.notes == NOTES
    assert cached.output.output == OUTPUT
    restores.assert_not_called()


def test_read_missing_field_restores_from_disk(evicted, model_cache_enabled, restores):
    uncached = load_uncached(evicted.path)

    assert evicted.output.output == uncached.output.output == OUTPUT
    assert evicted.trace == uncached.trace
    assert evicted.body == BODY
    assert restores.call_count == 1
    assert model_cache_enabled.stats().records_with_large_values == 1


def test_restore_reads_all_large_fields_once(evicted, restores):
    evicted.trace
    evicted.body
    evicted.output.output
    evicted.model_dump()

    assert restores.call_count == 1


# A materialized content-parts list matches no member of the content union, so each
# dump warns; materialize_lazy_content documents this as cosmetic.
@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings")
def test_restore_materializes_trace_content(parent, model_cache_enabled):
    parts_trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
    ]
    record = load_cached(save_record(parent, trace=parts_trace))
    evict_large_values(model_cache_enabled)

    trace = record.trace
    assert trace is not None
    assert isinstance(trace[0]["content"], list)
    first, second = record.model_dump_json(), record.model_dump_json()
    assert first == second
    assert '"text":"Hello"' in first


@pytest.mark.parametrize("evict", [False, True], ids=["in_store", "evicted"])
def test_dump_includes_missing_fields(cached, model_cache_enabled, evict):
    if evict:
        evict_large_values(model_cache_enabled)
    uncached = load_uncached(cached.path)

    assert cached.model_dump() == uncached.model_dump()
    assert cached.model_dump_json() == uncached.model_dump_json()
    assert cached.model_dump(exclude_unset=True) == uncached.model_dump(
        exclude_unset=True
    )
    adapter = TypeAdapter(list[LazyRecord])
    assert adapter.dump_json([cached]) == adapter.dump_json([uncached])
    assert "body" not in cached.__dict__


def test_save_after_detach_writes_every_field(evicted):
    original = evicted.path.read_text(encoding="utf-8")

    copy = evicted.mutable_copy()
    copy.name = "renamed"
    copy.save_to_file()

    assert copy.path == evicted.path
    assert evicted.path.read_text(encoding="utf-8") == original.replace(
        '"name": "first"', '"name": "renamed"'
    )


def test_save_context_reaches_attachments(evicted, tmp_path):
    source = tmp_path / "attachment.txt"
    source.write_text("attached")

    copy = evicted.model_copy(
        update={"attachment": KilnAttachmentModel.from_file(source)}
    )
    assert copy.has_unloaded_fields()
    copy.save_to_file()

    saved = json.loads(evicted.path.read_text(encoding="utf-8"))
    attachment_path = evicted.path.parent / saved["attachment"]["path"]
    assert not Path(saved["attachment"]["path"]).is_absolute()
    assert attachment_path.read_text() == "attached"
    assert saved["body"] == BODY


def test_model_copy_update_keeps_update(evicted):
    copy = evicted.model_copy(update={"trace": None})

    dumped = copy.model_dump()
    assert dumped["trace"] is None
    assert dumped["body"] == BODY
    assert dumped["output"]["output"] == OUTPUT
    assert (
        evicted.model_dump()["trace"]
        == load_uncached(evicted.path).model_dump()["trace"]
    )


def test_model_copy_update_computes_summaries_live(evicted, restores):
    assert evicted.model_copy().trace_length == 2
    assert evicted.model_copy(update={"name": "renamed"}).trace_length == 2
    restores.assert_not_called()

    assert evicted.model_copy(update={"trace": None}).trace_length == 0
    assert (
        evicted.model_copy(update={"output": LazyOutput(output="new")}).output_preview
        == "new"
    )
    assert evicted.trace_length == 2


def test_deepcopy_is_complete_and_independent(evicted):
    copy = deepcopy(evicted)

    assert copy._lazy is None
    assert copy.output._lazy is None
    assert {"body", "notes", "trace"} <= copy.__dict__.keys()
    assert "output" in copy.output.__dict__
    assert copy.__dict__["_last_validated_body"] == BODY
    assert copy.__pydantic_private__ is not None
    assert copy.__pydantic_private__["_validated_output"] == OUTPUT
    assert copy.model_fields_set == evicted.model_fields_set
    assert copy.notes is not None and evicted.notes is not None
    copy.notes["source"] = "changed"
    assert evicted.notes == NOTES


def test_mutable_cache_hit_is_complete(cached):
    mutable = LazyRecord.load_from_file(cached.path)

    assert mutable is not cached
    assert mutable._readonly is False
    assert mutable._lazy is None
    assert not mutable.has_unloaded_fields()
    assert mutable.model_dump() == load_uncached(cached.path).model_dump()


@pytest.mark.parametrize("evict", [False, True], ids=["in_store", "evicted"])
def test_equality_with_fresh_load(cached, model_cache_enabled, evict):
    if evict:
        evict_large_values(model_cache_enabled)
    uncached = load_uncached(cached.path)

    assert cached == uncached
    assert uncached == cached
    assert cached.output == uncached.output
    assert cached != uncached.model_copy(update={"body": "different"})
    assert cached != uncached.mutable_copy()
    assert cached != "not a model"


def test_iter_yields_every_field(evicted):
    assert dict(evicted) == dict(load_uncached(evicted.path))


def test_repr_does_not_read_files(evicted, restores):
    text = repr(evicted)

    assert "body=<not loaded>" in text
    assert "output=<not loaded>" in text
    assert "name='first'" in text
    restores.assert_not_called()


def test_pickle_round_trip_is_complete(evicted):
    restored = pickle.loads(pickle.dumps(evicted))

    assert restored._lazy is None
    assert "body" in restored.__dict__
    assert restored == load_uncached(evicted.path)


def test_restore_deleted_file_raises(evicted):
    evicted.path.unlink()

    with pytest.raises(LargeFieldUnavailableError, match="no longer exists") as error:
        evicted.body
    assert error.value.path == evicted.path
    assert error.value.field == "body"
    assert isinstance(error.value.__cause__, FileNotFoundError)

    with pytest.raises(LargeFieldUnavailableError) as nested_error:
        evicted.output.output
    assert nested_error.value.field == "output.output"


@pytest.mark.parametrize(
    "contents, cause",
    [("{not json", json.JSONDecodeError), ('{"name": "no body"}', ValidationError)],
    ids=["invalid_json", "invalid_record"],
)
def test_restore_invalid_file_raises(evicted, contents, cause):
    evicted.path.write_text(contents)

    with pytest.raises(LargeFieldUnavailableError) as error:
        evicted.notes
    assert isinstance(error.value.__cause__, cause)


def test_unavailable_record_raises_from_dumps_copies_and_saves(evicted):
    evicted.path.unlink()

    for use in (
        evicted.model_dump,
        evicted.model_dump_json,
        lambda: evicted == evicted.model_copy(),
        lambda: deepcopy(evicted),
        evicted.model_copy(update={"name": "renamed"}).save_to_file,
    ):
        with pytest.raises(LargeFieldUnavailableError, match="no longer exists"):
            use()
    assert not evicted.path.exists()


def test_dump_inside_another_serializer_raises_naming_the_file(evicted):
    """pydantic wraps errors raised while serializing; the message keeps the path."""
    evicted.path.unlink()

    with pytest.raises(PydanticSerializationError, match="no longer exists") as error:
        TypeAdapter(list[LazyRecord]).dump_json([evicted])
    assert str(evicted.path) in str(error.value)


def test_restore_changed_file_returns_new_values(
    evicted, model_cache_enabled, restores
):
    new_trace = [{"role": "user", "content": "A different question"}]
    rewrite(evicted.path, trace=new_trace)

    assert evicted.trace == new_trace
    assert evicted.name == "first"
    assert model_cache_enabled.stats().records == 0
    assert evicted.body == BODY
    assert evicted.trace == new_trace
    assert restores.call_count == 1


def test_restore_shape_change_raises(parent, model_cache_enabled):
    record = load_cached(
        save_record(parent, repaired_output=LazyOutput(output="repaired"))
    )
    evict_large_values(model_cache_enabled)
    rewrite(record.path, repaired_output=None)

    with pytest.raises(
        LargeFieldUnavailableError, match="'repaired_output' is no longer set"
    ):
        record.repaired_output.output


def test_mutable_copy_of_changed_file_reloads(cached, restores):
    rewrite(cached.path, name="changed", body="A new body")

    copy = cached.mutable_copy()

    assert (copy.name, copy.body) == ("changed", "A new body")
    assert copy._readonly is False
    assert copy._lazy is None
    restores.assert_not_called()


def test_mutable_copy_of_unchanged_record_does_not_reload(cached, restores):
    with patch.object(
        LazyRecord, "load_from_file", wraps=LazyRecord.load_from_file
    ) as load:
        copy = cached.mutable_copy()

    load.assert_not_called()
    restores.assert_not_called()
    assert copy == load_uncached(cached.path).mutable_copy()


def test_mutable_copy_of_deleted_file_keeps_cached_values(cached):
    expected = load_uncached(cached.path).model_dump()
    cached.path.unlink()

    assert cached.mutable_copy().model_dump() == expected


def test_mutable_copy_of_deleted_file_after_evicting_raises(evicted):
    evicted.path.unlink()

    with pytest.raises(LargeFieldUnavailableError, match="no longer exists"):
        evicted.mutable_copy()


def test_mutable_copy_of_deleted_file_after_reading_a_newer_version_raises(evicted):
    rewrite(evicted.path, name="new name", body="A new body")
    assert evicted.body == "A new body"
    assert evicted.name == "first"
    evicted.path.unlink()

    with pytest.raises(LargeFieldUnavailableError, match="newer version"):
        evicted.mutable_copy()


def test_orphan_keeps_local_values(cached, model_cache_enabled, restores):
    model_cache_enabled.clear()

    assert cached.body == BODY
    assert cached.output.output == OUTPUT
    assert cached.model_dump() == load_uncached(cached.path).model_dump()
    assert restores.call_count == 1
    assert model_cache_enabled.stats().records == 0


def test_large_values_bigger_than_budget_are_not_kept(
    parent, model_cache_enabled, monkeypatch, restores
):
    path = save_record(parent, body="x" * 50_000)
    load_cached(path)
    entry = model_cache_enabled._records[path]
    budget = (entry.normal_bytes + entry.large_bytes) // 2
    assert entry.normal_bytes < budget < entry.large_bytes
    small_cache = ModelCache(enabled=True, budget_bytes=budget)
    monkeypatch.setattr(ModelCache, "_shared_instance", small_cache)

    record = load_cached(path)
    assert small_cache.stats().records == 1
    assert small_cache.stats().records_with_large_values == 0

    assert record.body == "x" * 50_000
    assert record.body == "x" * 50_000
    assert restores.call_count == 2
    assert small_cache.stats().records_with_large_values == 0


def test_concurrent_reads_and_eviction(parent, model_cache_enabled, run_racing_threads):
    paths = [
        save_record(parent, name=f"record {i}", body=f"{BODY} {i}") for i in range(12)
    ]
    expected = {path: load_uncached(path).model_dump_json() for path in paths}
    records = [load_cached(path) for path in paths]
    errors: list[BaseException] = []
    deadline = time.monotonic() + 0.5

    def read(seed: int) -> None:
        rng = random.Random(seed)
        try:
            while time.monotonic() < deadline:
                record = rng.choice(records)
                assert record.model_dump_json() == expected[record.path]
                assert record.output.output == OUTPUT
        except BaseException as error:
            errors.append(error)

    def evict() -> None:
        try:
            while time.monotonic() < deadline:
                evict_large_values(model_cache_enabled)
        except BaseException as error:
            errors.append(error)

    run_racing_threads(
        [threading.Thread(target=read, args=(seed,)) for seed in range(8)]
        + [threading.Thread(target=evict)]
    )

    assert errors == []


@pytest.mark.parametrize(
    "body", ["", "short", "exactly10!", "longer than ten characters"]
)
@pytest.mark.parametrize("trace", [None, TRACE], ids=["no_trace", "trace"])
def test_summary_values_match_live_values(
    parent, model_cache_enabled, restores, body, trace
):
    path = save_record(parent, body=body, trace=trace)
    record = load_cached(path)
    uncached = load_uncached(path)

    assert record.body_preview == uncached.body_preview == body[:10]
    assert record.trace_length == uncached.trace_length
    assert record.output_preview == uncached.output_preview
    assert record.output.output_length == uncached.output.output_length
    restores.assert_not_called()


def test_summary_values_not_serialized(cached):
    names = {"body_preview", "trace_length", "output_preview", "output_length"}

    assert names.isdisjoint(cached.model_dump())
    assert names.isdisjoint(cached.model_dump()["output"])
    for mode in ("validation", "serialization"):
        schema = json.dumps(LazyRecord.model_json_schema(mode=mode), ensure_ascii=False)
        assert not any(name in schema for name in names)


def schema_record_class(lazy: bool) -> type[BaseModel]:
    """A record class with or without the mixin and markers, for schema comparison."""
    if lazy:

        class SchemaOutput(LazyFieldsMixin, KilnBaseModel):
            output: Annotated[str, LargeField()] = Field(description="Output.")

        class SchemaRecord(LazyFieldsMixin, KilnBaseModel):
            body: Annotated[str, LargeField()] = Field(description="Body.")
            output: SchemaOutput
            repaired: SchemaOutput | None = None
            attachment: KilnAttachmentModel | None = None
            tags: list[str] = Field(default_factory=list)

            @summary_value
            def body_length(self) -> int:
                return len(self.body)

        return SchemaRecord

    class SchemaOutput(KilnBaseModel):
        output: str = Field(description="Output.")

    class SchemaRecord(KilnBaseModel):
        body: str = Field(description="Body.")
        output: SchemaOutput
        repaired: SchemaOutput | None = None
        attachment: KilnAttachmentModel | None = None
        tags: list[str] = Field(default_factory=list)

    return SchemaRecord


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_serialization_schema_unchanged(mode):
    lazy, plain = schema_record_class(lazy=True), schema_record_class(lazy=False)

    assert lazy.model_json_schema(mode=mode) == plain.model_json_schema(mode=mode)
    assert TypeAdapter(list[lazy]).json_schema(mode=mode) == TypeAdapter(
        list[plain]
    ).json_schema(mode=mode)


def test_has_unloaded_fields(cached):
    assert cached.has_unloaded_fields()
    assert not deepcopy(cached).has_unloaded_fields()
    assert not cached.model_copy(
        update={
            "body": "b",
            "notes": None,
            "trace": None,
            "output": LazyOutput(output="o"),
        }
    ).has_unloaded_fields()


def test_path_and_parent_assignment_leave_detached_record_unchanged(
    evicted, parent, restores
):
    own_keys = set(evicted.__dict__)
    private_keys = set(evicted.__pydantic_private__ or {})

    evicted.path = evicted.path
    evicted.parent = parent

    assert set(evicted.__dict__) == own_keys
    assert set(evicted.__pydantic_private__ or {}) == private_keys
    assert evicted.cached_parent() is parent
    restores.assert_not_called()
    assert evicted.model_dump() == load_uncached(evicted.path).model_dump()


@pytest.mark.parametrize("evict", [False, True], ids=["in_store", "evicted"])
def test_delete_cached_record(cached, model_cache_enabled, restores, evict):
    if evict:
        evict_large_values(model_cache_enabled)
    path = cached.path
    assert path is not None

    cached.delete()

    assert not path.parent.exists()
    assert cached.path is None
    assert model_cache_enabled.stats().records == 0
    restores.assert_not_called()


class SizedModel(BaseModel):
    text: str


def test_approx_value_size():
    assert approx_value_size("abc") == 52
    assert approx_value_size(b"ab") == 35
    assert {approx_value_size(v) for v in (None, True, 7, 1.5)} == {28}
    assert approx_value_size(["a", ("b",)]) == (56 + 16) + 50 + (56 + 8 + 50)
    assert approx_value_size({"k": 1}) == 64 + 40 + 50 + 28
    assert approx_value_size(SizedModel(text="a")) == 56 + 50
    marker = object()
    assert approx_value_size(marker) == sys.getsizeof(marker)

    deep: list[Any] = []
    for _ in range(100_000):
        deep = [deep]
    assert approx_value_size(deep) == 100_001 * 56 + 100_000 * 8


class ScalarRecord(LazyFieldsMixin, KilnBaseModel):
    flag: Annotated[bool, LargeField()]


def test_detach_keeps_attributes_that_share_a_scalar_value(
    tmp_path, model_cache_enabled
):
    path = tmp_path / "scalar_record.kiln"
    ScalarRecord(path=path, flag=True).save_to_file()

    record = ScalarRecord.load_from_file(path, readonly=True)

    assert "flag" not in record.__dict__
    assert record.__pydantic_private__ is not None
    assert record.__pydantic_private__["_readonly"] is True
    assert record.flag is True
