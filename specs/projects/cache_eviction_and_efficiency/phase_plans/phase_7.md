---
status: complete
---

# Phase 7: Benchmarks and Docs

## Overview

This phase adds the two benchmarks the architecture asks for: a memory benchmark (2,000 synthetic 20-turn runs, a 20 MB budget, accounted total against `tracemalloc`) and a warm `task.runs(readonly=True)` benchmark. It also covers the app's first-load path (readonly, cache on) in the existing load benchmark, writes the missing docstrings in `model_cache.py`, and brings the docs and agent guidance in line with the whole branch (run through the `docs-sync` skill, fork point to HEAD).

Measuring before writing the benchmarks, against the fork point (`65d47311`) with the cache forced on there, found three gaps the benchmarks would fail on:

- **Memory estimate.** A cached `TaskRun` without its large values takes about 18 KiB, whatever its size. The estimate counts `max(1.3 × file size − large values, 1 KiB)`, which is about 1 KiB for most runs. With 2,000 runs the cache held 42 MB of real memory against 19.6 MB accounted (2.2×). Half of the 18 KiB is `DataSource._data_source_properties`: pydantic treats the class-level table as a private attribute and deep-copies its seven models into every `DataSource`, two per run. That copy is also about a third of every run's load time.
- **Warm list loads** are about 25% slower than the fork point (18 µs per run against 14 µs). Each hit now does three `Path`-keyed dict operations (Python-level `__hash__` and `__eq__`) and builds a `FileIdentity`, where the old cache did one lookup and one `st_mtime_ns` read.
- **First readonly loads with the cache on** are 10–20% slower than the fork point, because `detach_large_values` walks every large value with `approx_value_size`.

The fixes are local: the `DataSource` table becomes a `ClassVar`, the cache keys its dicts by string and checks the stat result without building a `FileIdentity`, `approx_value_size` dispatches on the exact type first, and `MIN_RECORD_BYTES` is tuned to the measured footprint.

## Steps

1. **`libs/core/kiln_ai/datamodel/task_output.py`**: `DataSource._data_source_properties` becomes `ClassVar[tuple[DataSourceProperty, ...]]`, a tuple, so every instance shares the one table.

2. **`libs/core/kiln_ai/datamodel/model_cache.py`**:
   - `_cache_key(path: Path) -> str`, returning `os.path.normcase(path)`. `_records: OrderedDict[str, _Entry]` and `_loaded: OrderedDict[str, None]`. Each public method that takes a path converts it once; the private helpers (`_remove`, `_load_large_values`, `_drop_large_values`) take the key. `normcase` keeps Windows paths that differ only in case on one entry, as `Path` equality does there.
   - `FileIdentity.matches(self, st: os.stat_result) -> bool`. `_get_model` runs `os.stat(path)` (an `OSError` or `ValueError` counts as a changed file, as `from_path` does) and compares with `entry.identity.matches(st)`.
   - `MIN_RECORD_BYTES = 8 * 1024`, from the memory benchmark: a cached task run takes about 9 KiB without its large values once `DataSource` shares its table, an eval run about 6 KiB, chunk embeddings about 3 KiB.
   - Docstrings (pdoc attribute docstrings, a string literal after the assignment) for `MEMORY_FACTOR`, `MIN_RECORD_BYTES`, `MAX_BUDGET_BYTES`, `RAM_FRACTION`, `FALLBACK_BUDGET_BYTES` and `EVICTION_TARGET_FRACTION`. A class docstring for `ModelCache` (what it holds, the shared instance, the switch, that the methods are thread-safe and never do I/O under the lock) and a docstring for `stats()`.

3. **`libs/core/kiln_ai/datamodel/lazy_fields.py`**: `approx_value_size` checks `type(item)` against `str`, `dict`, `list`, `float`, `int`, `bool` and `None` first, then falls back to the current `isinstance` chain for subclasses, tuples, bytes, models and anything else. Results are unchanged.

4. **`libs/core/kiln_ai/datamodel/basemodel.py`**: the `readonly` line of the `load_from_file` docstring says what a readonly load returns with the cache on and off.

5. **Docs and agent guidance** (`docs-sync` over `origin/main...HEAD`):
   - `libs/core/README.md`: a "Caching Loaded Records" section under "Using the Kiln Data Model", with a table-of-contents entry: the cache is off in the library, `set_model_cache_enabled(True)` turns it on, readonly loads are shared and can't be edited, the memory budget.
   - `.agents/skills/kiln-conventions/references/server_desktop.md`: the "Process-wide state set by lifespan" gotcha and the startup table rows for `desktop_server.make_app`, the `kiln_server` script (the default lifespan turns the cache on) and the `kiln_mcp` script (turns the cache on).
   - `.agents/skills/kiln-conventions/references/core.md`, datamodel gotchas: the cache is off in the library and only hosts turn it on; readonly loads return the shared cached instance; large fields (`LargeField`, `LazyFieldsMixin` first in the bases, `summary_value`) and the hidden disk read; bulk readers load readonly; tests run with the cache off and take the root `conftest.py` fixtures (`model_cache_enabled`, `evict_large_values`, `large_field_restores`).
   - `pyproject.toml`: remove the `filterwarnings` entry and comment for the "File system does not support fine-grained timestamps" warning, which no longer exists.
   - Re-run `.agents/claude/setup.sh` so `.claude/skills` matches `.agents/skills`.

## Tests

`libs/core/kiln_ai/datamodel/test_model_perf.py` (a shared helper writes one saved run's JSON under many ids, so building 2,000 run files takes well under a second):
- `test_benchmark_cache_memory`: 2,000 synthetic 20-turn runs with reasoning, loaded readonly one at a time into a `ModelCache(enabled=True, budget_bytes=20 MiB)`. The accounted total never exceeds the budget; at the end some but not all records hold their large values; `tracemalloc`'s retained size is within 50% of the accounted total.
- `test_benchmark_warm_list_load`: 1,000 runs, cache on and warm; `task.runs(readonly=True)` stays under 100 µs per run (about 15 µs on a Linux dev machine; Windows stats are slower).
- `test_benchmark_load_from_file` parametrized over the library's mutable cache-off load and the app's readonly cache-on load, with the existing floor.

`libs/core/kiln_ai/datamodel/test_model_cache.py`:
- Helpers that read `_records` / `_loaded` go through `_cache_key`. The detached-record constants grow so their normal part stays above the new `MIN_RECORD_BYTES`.
- `test_file_identity_matches_stat`: true for the stat of the same file, false when the modified time, size or file id differs.
- The existing change-detection tests (changed modified time, size and file id, deleted file) cover the new hit path unchanged.

`libs/core/kiln_ai/datamodel/test_lazy_fields.py`:
- `test_approx_value_size` also covers a `str` subclass (a `str` enum), an `int` subclass and a `dict` subclass, which take the fallback path.
- The test that reads `_records[path]` goes through `_cache_key`.

`libs/core/kiln_ai/datamodel/test_datasource.py`:
- `test_data_source_property_table_shared_by_instances`: two `DataSource` instances read the same table object, and it isn't a private attribute.
