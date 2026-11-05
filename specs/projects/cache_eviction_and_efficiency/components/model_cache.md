---
status: draft
---

# Component: Model Cache

## Purpose and Scope

`ModelCache` (`libs/core/kiln_ai/datamodel/model_cache.py`) keeps parsed readonly records in memory, keyed by file path. This project adds four things:

- change detection that works on every platform;
- one memory budget with least-recently-used eviction, large values first;
- a store for large values, implementing `LargeValueSource` for [`lazy_fields.md`](lazy_fields.md);
- a process-wide on/off switch, off by default.

It does **not**:
- parse or validate files (`basemodel.load_from_file` does that);
- decide which fields are large (`lazy_fields`);
- watch the file system;
- run background threads or timers.

## Public Interface

```python
# libs/core/kiln_ai/datamodel/model_cache.py

@dataclass(frozen=True)
class FileIdentity:
    mtime_ns: int
    size: int
    inode: int
    @classmethod
    def from_stat(cls, st: os.stat_result) -> "FileIdentity": ...
    @classmethod
    def from_path(cls, path: Path) -> "FileIdentity | None": ...   # None if stat fails

@dataclass(frozen=True)
class CacheStats:
    records: int
    records_with_large_values: int
    total_bytes: int
    budget_bytes: int

class ModelCache:
    def __init__(self, *, enabled: bool = False, budget_bytes: int | None = None) -> None: ...
        # budget_bytes None -> default_cache_budget_bytes(). Tests pass small budgets.

    @classmethod
    def shared(cls) -> "ModelCache": ...                    # process-wide instance, created disabled

    @property
    def enabled(self) -> bool: ...
    def set_enabled(self, value: bool) -> None: ...         # turning off also clears

    def get_model(self, path: Path, model_type: type[T], readonly: bool = False) -> T | None: ...
    def get_model_id(self, path: Path, model_type: type[KilnBaseModel]) -> str | None: ...
    def set_model(
        self, path: Path, model: KilnBaseModel, identity: FileIdentity,
        detached: DetachedValues | None,
    ) -> None: ...
    def invalidate(self, path: Path) -> None: ...
    def clear(self) -> None: ...
    def stats(self) -> CacheStats: ...

    # LargeValueSource (used by lazy_fields)
    def large_values_for(self, root: LazyFieldsMixin) -> Mapping[FieldPath, Any] | None: ...
    def store_restored_values(
        self, root: LazyFieldsMixin, identity: FileIdentity, values: Mapping[FieldPath, Any], size: int
    ) -> bool: ...
    def is_current_entry(self, root: LazyFieldsMixin) -> bool: ...

def set_model_cache_enabled(value: bool) -> None: ...   # ModelCache.shared().set_enabled(value)
def model_cache_enabled() -> bool: ...
def default_cache_budget_bytes() -> int: ...            # min(2 GiB, 20% of physical RAM)
def physical_memory_bytes() -> int | None: ...
```

### Signature changes

- `set_model` takes a `FileIdentity` instead of `mtime_ns: int`, plus the optional `DetachedValues`.
- `_check_timestamp_granularity` and its tests are deleted.
- `get_model`'s behavior is unchanged, including `ValueError` on a type mismatch and the mutable copy on `readonly=False`.

## Internal Design

### Entries

```python
@dataclass
class _Entry:
    model: KilnBaseModel
    identity: FileIdentity
    normal_size: int                       # bytes counted for the record without large values
    large_size: int                        # bytes counted for large values when loaded (0 if none)
    large_values: Mapping[FieldPath, Any] | None   # None = evicted, or class has no large fields
```

State, guarded by one `threading.RLock`:
- `_records: OrderedDict[Path, _Entry]`: every entry, least recently used first.
- `_loaded: OrderedDict[Path, None]`: entries whose `large_values` are in memory, least recently used first.
- `_total: int`: the sum of `normal_size` over `_records`, plus the sum of `large_size` over `_loaded`.

The lock is never held during file I/O, parsing or validation. Inside the lock, every operation is a constant number of dict or `OrderedDict` steps, plus eviction pops.

### Size estimates

`set_model` computes:
- `file_size = identity.size`
- If `detached` is `None`, the class has no large fields: `normal_size = int(file_size * MEMORY_FACTOR)` and `large_size = 0`.
- Otherwise: `large_size = detached.size` and `normal_size = max(int(file_size * MEMORY_FACTOR) - large_size, MIN_RECORD_BYTES)`.

The starting values are `MEMORY_FACTOR = 1.3` (measured 1.15–1.5) and `MIN_RECORD_BYTES = 1024`. Both are module constants, tuned by the memory benchmark.

### Change detection

`get_model` and `get_model_id`, under the lock:
1. Look up the entry. On a miss, return `None`.
2. Release the lock and run `FileIdentity.from_path(path)`, which is one `os.stat`.
3. Re-acquire the lock. If the stat failed, the identity differs, or the entry was replaced meanwhile, `invalidate(path)` and return `None`.
4. Run the type check, which raises `ValueError` as today.
5. `move_to_end` in `_records`. `get_model_id` does the same move.
6. Return the model (readonly), or `model.mutable_copy()` (mutable). The copy happens outside the lock.

`load_from_file` takes the identity from `os.fstat` on the open file descriptor, as it does today with the modified time. The identity it stores therefore matches the bytes it read.

### Adding an entry

`set_model(path, model, identity, detached)`:
1. If not enabled, return.
2. Raise `RuntimeError` if `model._readonly` is false. This is unchanged.
3. Under the lock: if an entry for `path` exists, remove it first (see "Removing" below).
4. Insert the new `_Entry` at the end of `_records` and add `normal_size` to `_total`.
5. If `detached` is given and `large_size <= budget_bytes`, set `large_values = detached.values`, append to `_loaded` and add `large_size` to `_total`. If `large_size > budget_bytes`, leave `large_values = None`. The record is served, but its large values aren't kept.
6. If `_total > budget_bytes`, run `_evict()`.

### Eviction

`_evict()` is called with the lock held, only when `_total > budget_bytes`.

```python
target = int(budget_bytes * 0.9)
while _total > target and _loaded:
    path, _ = _loaded.popitem(last=False)
    entry = _records[path]
    entry.large_values = None
    _total -= entry.large_size
while _total > target and _records:
    path, entry = _records.popitem(last=False)
    _total -= entry.normal_size
log.debug(...)  # counts only
```

- Evicting never touches the record object. It drops the cache's references to values, and any caller holding one keeps it.
- An evicted record is still held by its callers. Its lazy fields keep working: they restore from disk, and the record keeps the values itself, because it's no longer the cache's entry.

### Reading and storing large values

`large_values_for(root)`, under the lock:
- Find the entry for `root._lazy.root_info.path`.
- If it doesn't exist, or `entry.model is not root`, or `entry.large_values is None`, return `None`.
- Otherwise `move_to_end` in both `_loaded` and `_records`, and return `entry.large_values`.

`store_restored_values(root, identity, values, size)`, under the lock:
- Find the entry for `root`'s path.
- Return `False` without storing if any of these hold:
  - there's no entry, or `entry.model is not root`;
  - `identity != entry.identity`;
  - `size > budget_bytes`.
- If `entry.large_values` is already set (another thread restored first), `move_to_end` and return `True`. The caller still returns its own equal values.
- Otherwise set `large_values` and `large_size = size`, append to `_loaded`, add to `_total`, run `_evict()` if over budget, and return `True`.

`is_current_entry(root)`: under the lock, whether the entry for `root`'s path exists and `entry.model is root`.

### Removing

`invalidate(path)` and the entry replacement inside `set_model`, under the lock:
- Pop the entry from `_records`. If it was in `_loaded`, pop it there too and subtract `large_size`.
- Subtract `normal_size`.

`clear()` empties both dicts and sets `_total = 0`. Existing callers are unchanged: `save_to_file`, `delete`, `memory.py`, and `migrate_eval_runs.py`.

### On/off switch

- `ModelCache.shared()` creates the instance with `enabled=False`.
- `set_enabled(False)` clears the cache.
- `set_enabled(True)` on an already-enabled cache changes nothing.
- When disabled: `get_model` and `get_model_id` return `None`; `set_model` does nothing; `large_values_for` returns `None`; `store_restored_values` returns `False`.

`basemodel.load_from_file` checks `ModelCache.shared().enabled` before calling `detach_large_values`, so a cache-off load never creates lazy state.

### Budget

`default_cache_budget_bytes()` returns `min(2 * 1024**3, int(0.2 * ram))`, where `ram = physical_memory_bytes()`. If `ram` is `None`, it returns `1 * 1024**3`. It's computed in `ModelCache.__init__` and fixed for the instance's life.

`physical_memory_bytes()`:
- **POSIX** (Linux, macOS): `os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")`.
- **Windows:** `ctypes.windll.kernel32.GlobalMemoryStatusEx` with a `MEMORYSTATUSEX` struct, returning `ullTotalPhys`.
- Any exception or non-positive result gives `None`.

There's no new dependency.

### Thread safety

- All bookkeeping happens under one `RLock`; I/O never does.
- Records are immutable once published. That's the core rule in `lazy_fields.md`.
- Values stored in `large_values` are treated as immutable. Readers get the same objects, as they do today with cached records.
- A read can race with eviction. A reader that got `large_values` before eviction keeps a valid mapping. A reader after eviction restores from disk.

## Dependencies

- **Depends on:** `lazy_fields` (`DetachedValues`, `FieldPath` and `LazyFieldsMixin`, typing only); `basemodel.KilnBaseModel` (typing only, as today).
- **Depended on by:** `basemodel` (load, save, delete, id lookups, `mutable_copy`'s staleness check through `FileIdentity`); `lazy_fields` (through `LargeValueSource`); `memory.py`, `memory_store.py` and `migrate_eval_runs.py` (`invalidate`, `get_model_id`); hosts (`set_model_cache_enabled`).

## Test Plan

In `libs/core/kiln_ai/datamodel/test_model_cache.py` (rewritten). Each test uses its own `ModelCache(enabled=True, budget_bytes=...)`.

- `test_disabled_by_default`: `ModelCache.shared()` starts disabled; `set_model` stores nothing and `get_model` returns `None`.
- `test_set_enabled_false_clears`
- `test_set_model_cache_enabled_switch`: the module functions read and write the shared instance.
- `test_hit_returns_same_instance_readonly_and_copy_mutable`
- `test_changed_mtime_invalidates`, `test_changed_size_invalidates`, `test_replaced_file_new_inode_invalidates`: the last replaces the file with one of the same size and resets its mtime with `os.utime`, so only the inode differs.
- `test_deleted_file_invalidates`
- `test_wrong_type_raises_and_invalidates`: unchanged behavior.
- `test_accounting_matches_entries`: after a random series of set, get, store, evict and invalidate calls, `stats().total_bytes` equals the sum recomputed from the entries.
- `test_eviction_takes_large_values_first`: when over budget, large values are evicted least recently used first. Normal records are evicted only once none are left.
- `test_eviction_stops_at_ninety_percent`
- `test_under_budget_add_does_not_evict`: adds under budget never call `_evict`, checked with a spy.
- `test_get_touches_lru_order`: reading an old record protects it from the next eviction.
- `test_large_value_access_touches_lru_order`
- `test_record_larger_than_budget_served_not_kept`
- `test_store_restored_values_rejects_stale_identity`
- `test_store_restored_values_rejects_replaced_entry`: the entry was replaced by a newer load, so `False`, and `is_current_entry` is false.
- `test_store_restored_values_second_writer_keeps_first`
- `test_invalidate_subtracts_sizes`
- `test_default_budget_formula`: patched `physical_memory_bytes` with 4 GiB, 16 GiB and `None` gives 819 MiB (20% of 4 GiB), 2 GiB and 1 GiB.
- `test_physical_memory_bytes_positive`: real call on the test machine.
- `test_concurrent_get_set_invalidate`: 8 threads at random over 200 paths with a tiny budget. No exceptions, and the accounting invariant holds at the end.
- `test_benchmark_get_model`: kept. A hit must still exceed 25k operations per second.

In `libs/core/kiln_ai/datamodel/test_basemodel.py`:
- `test_load_from_file_stores_identity`
- `test_cache_off_load_has_no_lazy_state`
- `test_cache_on_load_detaches_large_values`

Host tests:
- `app/desktop/studio_server/test_server.py`, next to the strict-mode lifespan tests: the desktop lifespan enables the cache and restores the previous value.
- `libs/server/kiln_server/test_server.py` (new file): the default lifespan enables the cache, and a caller-supplied lifespan replaces it.
- `libs/server/kiln_server/mcp/test_mcp_server.py`: `main` enables the cache.
