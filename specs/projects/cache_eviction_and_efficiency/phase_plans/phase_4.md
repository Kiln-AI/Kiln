---
status: complete
---

# Phase 4: Lazy Fields Core

## Overview

This phase builds the machinery that lets a cached record keep its large field values out of memory and bring them back on demand, while staying an ordinary pydantic model to every consumer. No real datamodel field is marked yet (that's phase 5); everything is tested on small test models in `test_lazy_fields.py`.

It adds `lazy_fields.py` (marker, plan, summary values, detach, resolve, restore, serializer, schema override, copies, equality), the cache's large-value store with large-values-first eviction, the load integration in `load_from_file`, and `mutable_copy` rebuilding from a changed file.

Two facts found while planning shape the details:

- TaskRun's `_last_validated_input` / `_last_validated_output` are undeclared underscore names, so pydantic stores them in the instance `__dict__`, not in `__pydantic_private__`. The private-reference scrub checks both places.
- A per-instance state that points back at the root record makes a reference cycle (root → nested → state → root), so records and any restored values held on an orphan would be freed only by the cycle collector. Instead, every lazy instance in a record (and its shallow copies) shares one `_LazyRoot` object that holds the path, identity, source, a re-validate callable and any local values, and never references a record. The cache matches entries by this object (`owner`) instead of by `entry.model is root`. The `LargeValueSource` methods take `(path, owner)`.

## Steps

1. **New `libs/core/kiln_ai/datamodel/lazy_fields.py`.**
   - `FieldPath = tuple[str, ...]`.
   - `class LargeField` (`__slots__ = ()`): `Annotated` marker, no effect on validation, serialization or schema.
   - `class SummaryValue(Generic[M, T])` and `summary_value(fn) -> SummaryValue[M, T]`: a non-data descriptor with typed `__get__` overloads. On an instance with lazy state holding the name, returns the stored value; otherwise calls the function on live fields. `compute(obj)` calls the function. `LazyFieldsMixin.model_config = ConfigDict(ignored_types=(SummaryValue,))`, so pydantic doesn't treat it as a field (and a summary value on a non-lazy class fails at class creation).
   - `class LargeFieldUnavailableError(RuntimeError)` with `path: Path` and `field: str` (dotted), message naming both and the reason; the cause is chained.
   - `@dataclass(frozen=True) class LazyFieldPlan`: `paths` (every large leaf path through nested lazy models), `large_names` (this class's own marked fields), `nested_names` (fields holding one nested lazy model, `Optional` allowed), `summaries` (this class's `SummaryValue`s, subclass overrides win). `for_class(model_cls)` reads the plan from the class's own `__dict__` (`__lazy_field_plan__`) and builds and stores it on first use. A `LargeField`, or a lazy model with large fields, reachable only inside a list, dict, union of several types, or other generic raises `TypeError`.
   - `declares_large_field(model_cls) -> bool`: any field marked, directly or inside its annotation.
   - `class LargeValueSource(Protocol)`: `large_values_for(path, owner)`, `store_restored_values(path, owner, identity, values, size) -> bool`, `is_current_entry(path, owner) -> bool`, `drop_entry(path, owner)`.
   - `@dataclass(frozen=True) class DetachedValues`: `values: Mapping[FieldPath, Any]`, `size: int`, `owner: object`.
   - Internal `_LazyRoot` (slots: `path`, `identity`, `source`, `revalidate: Callable[[Any], BaseModel]`, `detached_paths`, `local_values`) and frozen `_LazyState` (slots: `root`, `prefix`, `missing: frozenset[str]`, `summary: Mapping[str, Any]`, `scrubbed: Mapping[str, FieldPath]`). Both return themselves from `__copy__` / `__deepcopy__`.
   - `detach_large_values(root, *, source, path, identity, revalidate) -> DetachedValues`: walk the lazy instances (root first, skipping `None` containers); compute every summary value on the complete tree; pop non-`None` large values from each instance's `__dict__`; scrub private attrs and non-field `__dict__` entries that are the same objects as popped values (recording `name -> path`); install a `_LazyState` on the root and on each nested instance that had anything removed, summarized or scrubbed. Size is `approx_value_size(values)`.
   - Resolving (`_tree_values(state, field)`): the root's `local_values` if set; else `source.large_values_for`; else `_restore`, then the decision table: not stale and stored → done; stale → `drop_entry`, keep as local values; not stored and not the current entry → local values; not stored but current (too big for the budget) → keep nothing.
   - `_restore(root, field)`: open the file, take `FileIdentity` from `os.fstat`, `json.loads`, call `root.revalidate(raw)` (the same `_validate_file_data` a load uses), and copy each detached path's leaf from the fresh record. A container that is now `None` raises `LargeFieldUnavailableError` (shape changed). `OSError` and `ValueError` (covers `JSONDecodeError` and `ValidationError`) are wrapped. Debug log on a stale (mixed old/new) read.
   - `approx_value_size(value)`: the per-type constants from the component doc, with an explicit stack.
   - `changed_lazy_root_file(model) -> Path | None`: for a lazy root whose file exists and has a different identity, its path.
   - `class LazyFieldsMixin(BaseModel)`:
     - `_lazy: _LazyState | None = PrivateAttr(default=None)`.
     - `__pydantic_init_subclass__`: `TypeError` if the class has any `model_serializer` other than the mixin's; builds the plan when the class is complete.
     - `__getattr__` under `if not TYPE_CHECKING:`: a missing large name resolves; everything else goes to pydantic's.
     - `@model_serializer(mode="wrap")`: when names are absent, serializes a short-lived stand-in instance with the filled `__dict__` (field order kept, so saved files keep their key order) and the same `fields_set`; never touches the shared record.
     - `__get_pydantic_json_schema__`: drops the `serialization` key from this class's own `model` core-schema node, then calls the handler.
     - `__deepcopy__`, `__eq__`, `__iter__`, `__getstate__`, `__repr_args__` per the component doc, built on one helper that returns the filled `__dict__` and the private dict with `_lazy=None` and scrubbed names put back.
     - `model_copy`: a shallow copy with an `update` gets a state without stored summary values, so its summaries come from its own fields.
     - `has_unloaded_fields()`: any large value in the tree absent from its instance's `__dict__`.
2. **`libs/core/kiln_ai/datamodel/model_cache.py`.**
   - `MIN_RECORD_BYTES = 1024`.
   - `_Entry` becomes a mutable slots dataclass: `model`, `identity`, `normal_bytes`, `large_bytes`, `large_owner`, `large_values`.
   - New `_loaded: OrderedDict[Path, None]` (entries with large values in memory, least recently used first). `_total_bytes` = sum of `normal_bytes` + `large_bytes` of loaded entries.
   - `set_model(path, model, identity, detached=None)`: with non-empty detached values, `normal_bytes = max(int(size * MEMORY_FACTOR) - detached.size, MIN_RECORD_BYTES)` and the values are kept if `detached.size <= budget`.
   - `_evict()` drops large values (LRU) first, then whole records, down to 90%; returns both counts; one debug log line.
   - `large_values_for`, `store_restored_values`, `is_current_entry`, `drop_entry` (the `LargeValueSource` protocol), all under the lock, matching by `entry.large_owner is owner`.
   - `CacheStats.records_with_large_values`.
   - Module docstring covers the large-value store.
3. **`libs/core/kiln_ai/datamodel/basemodel.py`.**
   - `load_from_file`: on a readonly load with the shared cache enabled and a `LazyFieldsMixin` class, call `detach_large_values(m, source=cache, path=path, identity=identity, revalidate=...)` and pass the result to `set_model`.
   - `KilnBaseModel.__pydantic_init_subclass__`: `TypeError` when a class declares a `LargeField` without `LazyFieldsMixin`.
   - `KilnBaseModel.mutable_copy`: if `changed_lazy_root_file(self)` returns a path, return `type(self).load_from_file(path)`.

## Tests

`libs/core/kiln_ai/datamodel/test_lazy_fields.py` (new). Test models: a parented root with a top-level large string, an optional large list, a materialized trace, a nested lazy model, an optional nested lazy model, an attachment, and validators that cache the validated values in a declared private attr and an undeclared `__dict__` attr.
- `test_plan_finds_top_level_and_nested_paths`
- `test_plan_rejects_marker_inside_list` (marker in `list[Annotated[...]]` and lazy model in `list[...]`)
- `test_marker_requires_mixin`
- `test_all_datamodel_markers_have_mixin` (walks every `BaseModel` class in `kiln_ai.datamodel`)
- `test_custom_model_serializer_rejected`
- `test_marker_has_no_effect_on_validation_or_dump`
- `test_cache_off_load_has_no_lazy_state` / `test_cache_on_load_detaches_large_values`
- `test_detach_removes_values_and_keeps_real_none`
- `test_detach_scrubs_private_references` (both storage spots; `tracemalloc` shows the large string freed once the store drops it)
- `test_read_missing_field_uses_store`
- `test_read_missing_field_restores_from_disk`
- `test_restore_reads_all_large_fields_once`
- `test_restore_materializes_trace_content`
- `test_dump_includes_missing_fields` (`model_dump`, `model_dump_json`, `exclude_unset`, `TypeAdapter(list[...]).dump_json`, key order)
- `test_save_after_detach_writes_every_field`
- `test_save_context_reaches_attachments`
- `test_model_copy_update_keeps_update`
- `test_model_copy_update_computes_summaries_live`
- `test_deepcopy_is_complete_and_independent`
- `test_mutable_cache_hit_is_complete`
- `test_equality_with_fresh_load` (and inequality after a change)
- `test_iter_yields_every_field`
- `test_repr_does_not_read_files`
- `test_pickle_round_trip_is_complete`
- `test_restore_deleted_file_raises` / `test_restore_invalid_file_raises` / `test_restore_invalid_record_raises`
- `test_restore_changed_file_returns_new_values`
- `test_restore_shape_change_raises`
- `test_mutable_copy_of_changed_file_reloads`
- `test_mutable_copy_of_unchanged_record_does_not_reload`
- `test_orphan_keeps_local_values`
- `test_large_values_bigger_than_budget_are_not_kept`
- `test_concurrent_reads_and_eviction`
- `test_summary_values_match_live_values`
- `test_summary_values_not_serialized`
- `test_serialization_schema_unchanged`
- `test_has_unloaded_fields`
- `test_approx_value_size` (constants, nesting, a 100k-deep list without recursion errors)

`libs/core/kiln_ai/datamodel/test_model_cache.py` (existing tests kept, helpers updated for the new entry fields):
- `test_eviction_takes_large_values_first`
- `test_large_value_access_touches_lru_order`
- `test_large_values_larger_than_budget_served_not_kept`
- `test_detached_entry_accounting`
- `test_store_restored_values_rejects_stale_identity`
- `test_store_restored_values_rejects_replaced_entry`
- `test_store_restored_values_second_writer_keeps_first`
- `test_store_restored_values_evicts_when_over_budget`
- `test_drop_entry_only_drops_owner`
- `test_large_value_methods_when_disabled`
- `test_removals_subtract_large_sizes`
- `test_accounting_matches_entries` and `test_concurrent_get_set_invalidate` extended with large values, stores and drops.

`libs/core/kiln_ai/datamodel/test_basemodel.py`:
- `test_load_from_file_stores_identity` updated for the `detached` argument.
