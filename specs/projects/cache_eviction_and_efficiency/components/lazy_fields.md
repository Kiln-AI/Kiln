---
status: draft
---

# Component: Lazy Fields

## Purpose and Scope

This component lets a cached record leave its large field values out of memory and bring them back on demand, while staying a normal pydantic model to every consumer.

It covers:
- the field marker;
- summary values;
- removing values when a record enters the cache;
- resolving a missing value on read;
- keeping serialization, copies, equality and the OpenAPI schema correct.

It does **not** decide when values are evicted or how much memory they may use. That's [`model_cache.md`](model_cache.md). It never touches records that aren't cached; a record built in memory or loaded with the cache off has no lazy state and behaves exactly as it does today.

## Core rule: never change a published record's `__dict__`

A cached record is shared by every reader, across threads. Once `load_from_file` has returned it, its `__dict__` is never changed again, by this component or by the cache.

The reason: pydantic-core walks the instance `__dict__` while serializing. If another thread inserted or deleted a key during that walk, the dump could fail or silently drop a field.

So:
- Large values are removed from `__dict__` **once**, in `detach_large_values`. That happens before the record is published.
- After that, large values live only in the cache's store, or in the record's own lazy state object.
- Restoring a value never writes it back into `__dict__`.
- Each lazy state attribute that can change is replaced in one assignment, with a fully built dict, so the swap happens at once under the GIL.

## Public Interface

```python
# libs/core/kiln_ai/datamodel/lazy_fields.py

FieldPath = tuple[str, ...]   # e.g. ("trace",), ("output", "output")

class LargeField:
    """Marker for Annotated: `input: Annotated[str, LargeField()] = Field(...)`.

    Has no effect on validation, serialization or JSON schema."""
    __slots__ = ()

class SummaryValue(Generic[M, T]):
    """Read-only descriptor made by @summary_value. Typed so `run.trace_length` is `int`."""
    def __init__(self, fn: Callable[[M], T]) -> None: ...
    @overload
    def __get__(self, obj: None, owner: type[M]) -> "SummaryValue[M, T]": ...
    @overload
    def __get__(self, obj: M, owner: type[M]) -> T: ...

def summary_value(fn: Callable[[M], T]) -> SummaryValue[M, T]: ...

class LargeFieldUnavailableError(RuntimeError):
    path: Path
    field: str            # dotted, e.g. "output.output"

class LazyFieldsMixin(BaseModel):
    """Opt-in base for models with LargeField fields or nested lazy models."""
    def has_unloaded_fields(self) -> bool: ...   # True if any large value isn't in this record's own __dict__

@dataclass(frozen=True)
class LazyFieldPlan:
    paths: tuple[FieldPath, ...]                  # leaf paths to every large field, through nested lazy models
    summary_names: dict[FieldPath, tuple[str, ...]]  # per lazy-instance prefix: its summary value names
    @classmethod
    def for_class(cls, model_cls: type[BaseModel]) -> "LazyFieldPlan": ...  # cached per class

class LargeValueSource(Protocol):
    """Implemented by ModelCache. Lets this module reach the store without importing model_cache."""
    def large_values_for(self, root: "LazyFieldsMixin") -> Mapping[FieldPath, Any] | None: ...
    def store_restored_values(
        self, root: "LazyFieldsMixin", identity: "FileIdentity", values: Mapping[FieldPath, Any], size: int
    ) -> bool: ...
    def is_current_entry(self, root: "LazyFieldsMixin") -> bool: ...
    def invalidate(self, path: Path) -> None: ...

@dataclass(frozen=True)
class DetachedValues:
    values: Mapping[FieldPath, Any]
    size: int                                     # approx_value_size of all values

def detach_large_values(
    root: "LazyFieldsMixin", *, source: LargeValueSource, path: Path, identity: "FileIdentity"
) -> DetachedValues: ...

def approx_value_size(value: Any) -> int: ...     # estimated in-memory bytes
```

`FileIdentity` comes from `model_cache.py`. It's imported for typing only; this module has no runtime import of `model_cache`.

## Internal Design

### The plan

`LazyFieldPlan.for_class` walks a class's `model_fields`:
- A field whose `FieldInfo.metadata` contains a `LargeField` adds a leaf path, `prefix + (name,)`.
- A field whose annotation, with `Optional`/`| None` removed, is a single `LazyFieldsMixin` subclass is walked with `prefix + (name,)`.
- A `LargeField` reachable only inside a `list`, `dict`, a union of several models, or a `TypeAdapter` type raises `TypeError` when the plan is built. To make a collection lazy, mark the collection field itself, the way `ChunkEmbeddings.embeddings` is marked.
- Summary value names are collected per lazy class, by scanning the class `__dict__` and bases for `SummaryValue` descriptors.

Plans are cached in a dict keyed by class and built on first use. The dict is guarded by a lock, so building happens once. `LazyFieldsMixin.__pydantic_init_subclass__` builds the plan eagerly, so marking mistakes fail at import.

Plans for the classes in this project:

| Root | Paths |
|---|---|
| `TaskRun` | `("input",)`, `("trace",)`, `("intermediate_outputs",)`, `("output","output")`, `("repaired_output","output")`, `("world_episode","final_state")` |
| `EvalRun` | `("input",)`, `("output",)`, `("task_run_trace",)`, `("judge_trace",)`, `("intermediate_outputs",)`, `("reference_answer",)` |
| `ChunkEmbeddings` | `("embeddings",)` |

`EvalRun` has no `world_episode` field. `EvalTaskInput.world_episode` is in a model that is never loaded from its own file, so it's never a root.

### Per-instance state

Every lazy instance in a cached tree (the root and each nested lazy instance) gets one private attribute, `_lazy: _LazyState | None` (a `PrivateAttr`, default `None`):

```python
class _LazyState:
    __slots__ = ("root", "prefix", "missing", "summary", "local_values", "scrubbed", "root_info")
    root: "LazyFieldsMixin"          # the cached root record (itself, for the root)
    prefix: FieldPath                # () for the root, ("output",) for run.output
    missing: frozenset[str]          # field names removed from this instance's __dict__
    summary: Mapping[str, Any]       # summary values computed before removal
    local_values: Mapping[str, Any] | None  # restored values kept on the instance (see "Orphans")
    scrubbed: Mapping[str, FieldPath]       # private attr name -> path of the large value it pointed to
    root_info: "_RootInfo | None"    # only on the root

@dataclass(frozen=True)
class _RootInfo:
    path: Path
    identity: FileIdentity
    source: LargeValueSource
```

`_LazyState` sits in `__pydantic_private__`, and pydantic never serializes private attributes. It defines `__deepcopy__` and `__copy__` to return itself, since it's treated as immutable and `local_values` is only ever replaced whole. That way, copying a record never copies or walks the root.

### `detach_large_values` (called once, before publishing)

1. Read `plan = LazyFieldPlan.for_class(type(root))`.
2. Compute every summary value on the root and on each nested lazy instance by calling the descriptor's function on the complete record. Store the results by prefix.
3. For each path in `plan.paths`, find the container instance by walking the prefix. Skip the path if a container on the way is `None`. Read the leaf value from `container.__dict__`. If it's `None`, keep it: real `None` values stay in `__dict__` and are never treated as missing. Otherwise, pop it into `values[path]`.
4. **Scrub private references.** For each lazy instance, compare each `__pydantic_private__` value by identity (`is`) with the popped values. Delete any match, and record `name -> path` in `scrubbed`. This catches `TaskRun._last_validated_input` and `_last_validated_output`, which hold the same string objects as `input` and `output.output`. Without the scrub, removing them from `__dict__` would free nothing.
5. Install a `_LazyState` on each lazy instance that had values removed or summary values computed. The root's state carries `root_info`.
6. Return `DetachedValues(values, approx_value_size(values))`.

### `__getattr__`: resolving a missing value

`LazyFieldsMixin.__getattr__` is defined inside `if not TYPE_CHECKING:`, the same way pydantic defines its own. That keeps type checkers from treating every attribute as `Any`. Python only calls `__getattr__` after normal lookup fails, so reading a present field costs nothing extra.

```python
def __getattr__(self, name):
    if name.startswith("_"):
        return super().__getattr__(name)          # pydantic private attrs
    state = _lazy_state(self)                      # reads __pydantic_private__ directly, no recursion
    if state is None or name not in state.missing:
        return super().__getattr__(name)
    return _resolve(self, state, name)
```

`_resolve(instance, state, name)`:
1. If `state.local_values` contains `name`, return it.
2. Set `root = state.root`, `info = root._lazy.root_info`, `key = state.prefix + (name,)`.
3. `values = info.source.large_values_for(root)`. This is a store hit, and it marks the entry as recently used. If not `None`, return `values[key]`.
4. Otherwise, run `_restore(root)` (below), which returns `(values, identity, stale)`.
5. Store the values with this decision table:

| Situation | Action |
|---|---|
| `stale` is false and `info.source.store_restored_values(root, identity, values, size)` returns `True` | The cache now holds them. |
| `stale` is true | Call `info.source.invalidate(info.path)`, then keep the values as local values (below). |
| `store_restored_values` returns `False` because `root` is no longer the cache's entry for the path | Keep the values as local values. |
| `store_restored_values` returns `False` because the record alone is larger than the budget | Keep nothing; the value is returned for this access only. |

6. Return `values[key]`.

**Local values** are only set when `info.source.is_current_entry(root)` is false, that is, when the record is an orphan the cache no longer holds. For each lazy instance in the tree, build that instance's `{name: value}` dict and assign `state.local_values` once. An orphan is held only by callers, so the memory belongs to them and is freed with the record. A record that is still the cache's entry never gets local values, because they would grow the cache past its budget without being counted.

### `_restore(root)`: re-read and re-validate

Restores use the **same validation as a fresh load**. Load-time transforms, such as `materialize_lazy_content` on traces, must apply to restored values exactly as they do on load. Re-implementing a "validate only these fields" path would risk subtle differences. The cost is that of a cold load, 1.4–4 ms for a 100-turn run.

1. Open `info.path` and take a `FileIdentity` from `os.fstat`, so the identity is read atomically with the content. Read the file, then `json.loads` it.
2. Call `fresh = type(root)._validate_file_data(raw, info.path, parent=root.cached_parent() if parented else None)`.
3. For each plan path, walk `fresh`. If the matching container exists on `root` but is `None` on `fresh`, the record's shape changed on disk, so raise `LargeFieldUnavailableError` ("changed on disk; reload the record"). Otherwise copy `fresh`'s leaf value into `values[path]`.
4. Set `stale = identity != info.identity`. If stale, log at debug level with the path. This is the accepted mixed read: normal fields from the old version, large fields from the new one.
5. Wrap these in `LargeFieldUnavailableError`, chaining the original: `FileNotFoundError`, `OSError`, `json.JSONDecodeError` and `ValidationError`.

`_restore` holds no lock while doing I/O or validation. Two threads may restore the same record at once. Both build equal values; `store_restored_values` keeps the first and ignores the second (see the cache component).

### Serialization: the wrap serializer

```python
@model_serializer(mode="wrap")
def _serialize_with_lazy_fields(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> Any:
    state = _lazy_state(self)
    if state is None:
        return handler(self)
    missing = [n for n in state.missing if n not in self.__dict__]
    if not missing:
        return handler(self)
    filled = {**self.__dict__, **{n: _resolve(self, state, n) for n in missing}}
    stand_in = type(self).model_construct(_fields_set=self.model_fields_set, **filled)
    return handler(stand_in)
```

- **Why a stand-in.** It's a complete, short-lived instance built without validation. The shared record's `__dict__` is never touched, which follows the core rule.
- **What `handler` keeps.** It carries the serialization info: mode, `include`/`exclude`, and the save context used by attachments. So `save_to_file`'s `model_dump_json(indent=2, exclude={"path"}, context=...)` behaves as it does today.
- **Nested models.** A nested lazy instance in `filled` (for example `run.output`) is still the shared nested object. Its own wrap serializer fills it the same way.
- **`model_copy(update=...)`.** The copy's `__dict__` may already hold a key listed in `state.missing`; for example `_split_judge_trace` sets `judge_trace=None`. The `n not in self.__dict__` filter keeps the update.

**Schema override.** A wrap `model_serializer` turns the model's serialization-mode JSON schema into `{}`, which would change the OpenAPI output (checked). `LazyFieldsMixin` defines `__get_pydantic_json_schema__`. It removes the `serialization` key only from the core-schema node whose `type == "model"` and `cls is cls`, then calls the handler. Checked: the serialization schema then matches a model without the serializer, including computed fields like `model_type`, and nested models' own field serializers.

This targeted strip differs from `CodeEvalProperties`' recursive one in `eval.py`, which removes every nested serializer. The recursive version must not be reused here.

**Serializer conflicts.** A class can have only one `model_serializer`. `LazyFieldsMixin.__pydantic_init_subclass__` raises `TypeError` if a subclass defines its own. None of the five lazy classes does today.

### Copies, equality, iteration, pickling, repr

All of these are defined on `LazyFieldsMixin`. They behave like today's models when `_lazy` is `None`.

| Method | Behavior when lazy |
|---|---|
| `__deepcopy__(memo)` | Builds a complete, independent instance. `__dict__` is deep-copied from `filled` (missing values resolved; nested lazy instances deep-copy through their own `__deepcopy__`). Private attrs are deep-copied, with `_lazy` set to `None` and every `scrubbed` name put back to the filled value at its path. `model_fields_set` is copied. The copy has no lazy state, and its validators' cached `_last_validated_*` values are back, so later assignments skip re-validation exactly as today. |
| `__copy__` | pydantic's default. A new instance with a shallow-copied `__dict__` and the same `_LazyState` object. Missing values keep resolving through the same root. |
| `__eq__(other)` | If neither side is lazy, pydantic's `__eq__`. Otherwise both sides must be the same type, have equal `model_fields_set`, and have equal filled `__dict__` mappings. Private attrs other than `_lazy` and the scrubbed names must also match. May read files. |
| `__iter__` | Yields `(name, value)` from the filled `__dict__`. |
| `__getstate__` | Like pydantic's, but with the filled `__dict__`, `_lazy` dropped and scrubbed private attrs put back. Unpickling gives a complete record. |
| `__repr_args__` | Yields present fields, plus `name=<not loaded>` for each missing one. Never reads files. |

`model_copy(deep=True)` goes through `__deepcopy__`, so `KilnBaseModel.mutable_copy()` returns a complete record.

### `mutable_copy` on a record whose file changed

`KilnBaseModel.mutable_copy` gains one check before copying. If `self` is a lazy root with `root_info`, and `FileIdentity.from_path(root_info.path) != root_info.identity`, it returns `type(self).load_from_file(root_info.path)`: a fresh, mutable, uncached load. This keeps the spec's rule that an editable copy never mixes versions.

For a lazy nested instance, `mutable_copy` isn't used: `TaskOutput` copies only happen as part of their root. A nested instance's `__deepcopy__` is complete either way.

### Summary values

```python
@summary_value
def trace_length(self) -> int:
    return len(self.trace) if self.trace else 0
```

`SummaryValue.__get__`: if the instance has `_lazy` state whose `summary` holds this name, return that. Otherwise call the function, which reads live fields. That only happens on records that aren't lazy, so it never triggers a restore.

Summary values are plain descriptors, not pydantic fields or `computed_field`s. They never appear in `model_dump`, on disk, or in the schema.

| Class | Name | Function |
|---|---|---|
| `TaskRun` | `input_preview: str \| None` | `RunSummary.format_preview(self.input)`. The 100-character truncation helper moves into `lazy_fields.py` as `preview_text(text, max_length=100)`, and `RunSummary.format_preview` calls it. |
| `TaskRun` | `output_preview: str \| None` | `preview_text(self.output.output)`, `None` when that output is empty. |
| `TaskRun` | `trace_length: int` | as above |
| `TaskRun` | `has_thinking: bool` | today's `thinking_training_data() is not None`, moved here. `has_thinking_training_data()` returns `self.has_thinking`. |
| `EvalRun` | `judge_trace_length: int` | `len(self.judge_trace) if self.judge_trace else 0` |
| `WorldEpisode` | `has_final_state: bool` | `self.final_state is not None` |

`TaskRun.thinking_training_data()` itself still reads `intermediate_outputs`; callers that need the text need the field.

### `approx_value_size`

Estimates the in-memory bytes of decoded JSON-like values without a full object walk:
- `str`: `49 + len(s)`; `bytes`: `33 + len(b)`
- `int`, `float`, `bool`, `None`: 28
- `list`/`tuple`: `56 + 8 * len` plus the items
- `dict`: `64 + 40 * len` plus keys and values
- pydantic `BaseModel`: `56` plus its `__dict__` values
- anything else: `sys.getsizeof`

It's recursive, with an explicit stack instead of Python recursion so deep traces don't hit the recursion limit. The memory benchmark (see the architecture) checks the total against `tracemalloc` and tunes the constants.

## Dependencies

- **Depends on:** pydantic v2 (`BaseModel`, `model_serializer`, `PrivateAttr`, `GetJsonSchemaHandler`); `FileIdentity` (typing only); `KilnBaseModel._validate_file_data` (called on the root by duck typing).
- **Depended on by:** `basemodel.load_from_file` (calls `detach_large_values`); `ModelCache` (implements `LargeValueSource`); the five lazy classes; `RunSummary`.

## Test Plan

In `libs/core/kiln_ai/datamodel/test_lazy_fields.py`, using small test models (a root with a top-level large field, a nested lazy model and an `Optional` nested lazy model) plus `TaskRun`.

- `test_plan_finds_top_level_and_nested_paths`: plan paths for the test root and for `TaskRun` match the table above.
- `test_plan_rejects_marker_inside_list`: a `LargeField` inside `list[Model]` raises `TypeError` at class creation.
- `test_marker_requires_mixin`: a `KilnBaseModel` subclass with a `LargeField` and no mixin raises `TypeError`.
- `test_all_datamodel_markers_have_mixin`: walks every `BaseModel` subclass in `kiln_ai.datamodel` and asserts any class with a marker subclasses `LazyFieldsMixin`.
- `test_custom_model_serializer_rejected`: a lazy class that defines its own `model_serializer` raises `TypeError`.
- `test_detach_removes_values_and_keeps_real_none`: after detach, non-`None` large values are absent from `__dict__`, `None` values stay present, and reading a `None` field never calls the source.
- `test_detach_scrubs_private_references`: `TaskRun._last_validated_input` / `_last_validated_output` are gone after detach, and `tracemalloc` shows the large strings freed once the store drops them.
- `test_read_missing_field_uses_store`: with a fake source holding the values, attribute reads return them and make no file reads.
- `test_read_missing_field_restores_from_disk`: with an empty source, a read re-validates the file once, offers the values to `store_restored_values`, and returns values equal to a fresh load, nested `output.output` included.
- `test_restore_reads_all_large_fields_once`: reading `trace` then `input` then `output.output` causes one file read.
- `test_restore_materializes_trace_content`: restored trace message `content` is a list, not a single-use iterator, and serializes the same twice.
- `test_dump_includes_missing_fields`: `model_dump()`, `model_dump_json()` and `TypeAdapter(list[TaskRun]).dump_json` equal a cache-off load's output.
- `test_save_after_detach_writes_every_field`: `mutable_copy()` of a detached record, edited and saved, gives a file equal to the original apart from the edit.
- `test_save_context_reaches_attachments`: `save_to_file` on a copy of a detached record that has an attachment still copies the attachment.
- `test_model_copy_update_keeps_update`: `model_copy(update={"judge_trace": None})` on a detached `EvalRun` dumps `judge_trace: null` and the other large fields in full.
- `test_deepcopy_is_complete_and_independent`: deep copy has no `_lazy`, every field is present, and the scrubbed private attrs are back.
- `test_equality_with_fresh_load`: a detached record `==` a fresh readonly load of the same file.
- `test_repr_does_not_read_files`: `repr()` shows `<not loaded>` and makes no reads.
- `test_pickle_round_trip_is_complete`
- `test_restore_deleted_file_raises`: `LargeFieldUnavailableError` names the path and field, and the cause is `FileNotFoundError`.
- `test_restore_invalid_file_raises`: the file is overwritten with invalid JSON, so the read raises `LargeFieldUnavailableError` with `JSONDecodeError` as the cause.
- `test_restore_changed_file_returns_new_values`: the file is rewritten with a new trace, so the read returns the new trace, the cache entry is invalidated, and repeat reads don't re-read the file.
- `test_restore_shape_change_raises`: `repaired_output` is present when cached and removed on disk, so reading `repaired_output.output` raises.
- `test_mutable_copy_of_changed_file_reloads`: after an outside rewrite, `mutable_copy()` returns the new version entirely.
- `test_orphan_keeps_local_values`: once the cache drops the entry, reads restore once and then keep the values on the instance.
- `test_concurrent_reads_and_eviction`: 8 threads read and dump random detached records while another thread evicts in a loop. Every dump equals the cache-off dump, and nothing raises.
- `test_summary_values_match_live_values`: for each summary value, the detached value equals the value computed on a cache-off load. Cases cover empty, short, exactly-100-character and long text, a missing trace, and `reasoning` vs `chain_of_thought`.
- `test_summary_values_not_serialized`: no summary value name appears in `model_dump()` or the JSON schema.
- `test_serialization_schema_unchanged`: for each lazy class, `model_json_schema(mode="serialization")` and `(mode="validation")` equal those of a copy of the class built without the mixin.

No automated test covers hiding `__getattr__` from type checkers. A negative type-check case can't live in the repo's checked code. Code review confirms `__getattr__` sits under `if not TYPE_CHECKING:`.
