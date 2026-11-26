---
status: complete
---

# Phase 3: Memory Budget and Eviction of Whole Records

## Overview

The cache has no size limit today. This phase gives it one: min(2 GiB, 20% of physical RAM), computed once when a `ModelCache` is built. Each entry carries a size estimate taken from its file size. The cache keeps a running total and a least-recently-used order. Adding a record costs one addition and one comparison; only when the total goes over budget does the cache evict whole records, oldest use first, down to 90% of the budget. A record larger than the whole budget is served to its caller but not kept.

There are no lazy fields yet, so every entry is a whole record and eviction drops whole records. Phase 4 adds the large-value store, which is evicted before whole records.

All bookkeeping moves under one `threading.RLock`. The lock is never held during the file stat or the mutable copy.

## Steps

1. `libs/core/kiln_ai/datamodel/model_cache.py`:
   - Module constants:
     ```python
     MEMORY_FACTOR = 1.3                       # in-memory bytes per file byte (measured 1.15–1.5)
     MAX_BUDGET_BYTES = 2 * 1024**3
     RAM_FRACTION = 0.2
     FALLBACK_BUDGET_BYTES = 1 * 1024**3       # when physical RAM can't be read
     EVICTION_TARGET_FRACTION = 0.9
     ```
   - `_Entry` gains `size: int` (estimated bytes: `int(identity.size * MEMORY_FACTOR)`). It stays frozen.
   - `CacheStats` frozen dataclass: `records: int`, `total_bytes: int`, `budget_bytes: int`. (`records_with_large_values` arrives with the large-value store in phase 4.)
   - `ModelCache.__init__(self, *, enabled: bool = False, budget_bytes: int | None = None)`. `None` → `default_cache_budget_bytes()`. State: `self._records: OrderedDict[Path, _Entry]` (least recently used first), `self._total_bytes: int`, `self._budget_bytes: int`, `self._lock = threading.RLock()`.
   - `_get_model(path, model_type)`:
     1. Disabled → `None`.
     2. Under the lock, look up the entry. Miss → `None`.
     3. Outside the lock, `FileIdentity.from_path(path)`.
     4. Under the lock: if `_records.get(path) is not entry` (removed or replaced meanwhile) → `None`, leaving any newer entry alone. If the identity differs → remove and `None`. Wrong type → remove and `ValueError`. Otherwise `move_to_end(path)` and return the model.
   - `get_model` unchanged in behavior; the mutable copy is made outside the lock. `get_model_id` goes through `_get_model`, so it touches the order too.
   - `set_model(path, model, identity)`: disabled → return; mutable model → `RuntimeError` (unchanged). Under the lock: remove any existing entry for `path`; if `size > budget_bytes`, stop (served, not kept); otherwise append the entry, add its size, and call `_evict()` only if `_total_bytes > _budget_bytes`.
   - `_evict()` (lock held): pop from the front of `_records`, subtracting sizes, until `_total_bytes <= int(budget * EVICTION_TARGET_FRACTION)`. One debug log line with the count evicted and the totals.
   - `_remove(path)` (lock held): pop the entry and subtract its size. `invalidate` takes the lock and calls it.
   - `clear()`: under the lock, empty `_records` and set `_total_bytes = 0`.
   - `stats() -> CacheStats`, under the lock.
   - Module functions:
     ```python
     def default_cache_budget_bytes() -> int: ...   # min(MAX_BUDGET_BYTES, int(RAM_FRACTION * ram)), FALLBACK_BUDGET_BYTES if ram is None
     def physical_memory_bytes() -> int | None: ... # POSIX sysconf; Windows GlobalMemoryStatusEx; None on error or non-positive
     ```
     The Windows branch sits under `if sys.platform == "win32":` and uses a local `ctypes.Structure` for `MEMORYSTATUSEX`. No new dependency.
   - Module docstring gains the budget and eviction contract.
   - `logger = logging.getLogger(__name__)`.
2. Root `conftest.py` `model_cache_enabled` fixture: `ModelCache(enabled=True, budget_bytes=1 GiB)`, so tests don't depend on the machine's RAM. Docstring says so.
3. No change to `basemodel.py`: `set_model` already receives the file's identity, which carries the size.

## Tests

`libs/core/kiln_ai/datamodel/test_model_cache.py` (existing tests kept; new tests use their own `ModelCache(enabled=True, budget_bytes=...)` and files of known size, so each record's estimate is `int(file_size * MEMORY_FACTOR)`):
- `test_entry_size_estimate_from_file_size`: one record's accounted size is `int(file_size * MEMORY_FACTOR)`.
- `test_under_budget_add_does_not_evict`: adds under budget never call `_evict` (spy); the add that crosses the budget calls it once.
- `test_eviction_removes_least_recently_used_first`
- `test_eviction_stops_at_ninety_percent`: after the over-budget add, the total is at or below 90% of the budget and only as many records as needed were dropped.
- `test_get_touches_lru_order`: reading the oldest record protects it from the next eviction.
- `test_get_model_id_touches_lru_order`
- `test_record_larger_than_budget_served_not_kept`: not stored, other entries untouched, and an older entry for the same path is dropped.
- `test_replacing_entry_subtracts_old_size`
- `test_invalidate_subtracts_sizes`
- `test_stale_and_wrong_type_removals_subtract_sizes`
- `test_clear_resets_accounting`
- `test_accounting_matches_entries`: a seeded random series of set, get, get_model_id, invalidate and file rewrites; after each step `stats().total_bytes` equals the sum recomputed from the entries and is within budget.
- `test_concurrent_get_set_invalidate`: 8 threads at random over 200 files with a budget of about 20 records. No exceptions, the accounting invariant holds at the end, and the total is within budget.
- `test_check_after_stat_ignores_entry_replaced_meanwhile`: an entry replaced between the lookup and the stat is neither served nor removed.
- `test_default_budget_formula`: patched `physical_memory_bytes` of 4 GiB, 16 GiB and `None` gives `int(0.2 * 4 GiB)`, 2 GiB and 1 GiB.
- `test_budget_defaults_to_default_cache_budget_bytes`: `ModelCache()` and `ModelCache.shared()` use `default_cache_budget_bytes()`; an explicit `budget_bytes` wins.
- `test_physical_memory_bytes_positive`: real call on the test machine (runs on all three OSes in the macOS/Windows job).
- `test_physical_memory_bytes_none_when_query_fails` and `test_physical_memory_bytes_none_when_not_positive`: POSIX only, `os.sysconf` patched.
- `test_benchmark_get_model`: kept; a hit must still exceed 25k operations per second.

`libs/core/kiln_ai/datamodel/test_basemodel.py`:
- `test_readonly_load_evicts_least_recently_used`: with a shared cache whose budget fits two records, three readonly loads leave the first evicted (a reload gives a new instance) and the other two cached.
- `test_readonly_load_larger_than_budget_is_served_not_cached`
