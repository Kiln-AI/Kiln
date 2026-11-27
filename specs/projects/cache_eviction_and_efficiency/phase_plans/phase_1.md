---
status: complete
---

# Phase 1: Cache On/Off and Change Detection

## Overview

Today the cache's startup check always fails on Linux, so the cache is off there, and on macOS and Windows it is on for every user of the library. This phase replaces the modified-time check with a three-part file identity (modified time, size, file id), deletes the broken Linux check, and makes the cache off by default with a process-wide switch. The three hosts (desktop app, `kiln_server`, `kiln_mcp`) turn it on in their own startup code. Tests run with the library default (off), and a root fixture turns it on for the tests that need it. A new CI job runs the full Python suite on macOS and Windows on release and by hand.

No budget, eviction or lazy fields yet (later phases). Single-pass validation (5a) is phase 2.

## Steps

1. `libs/core/kiln_ai/datamodel/model_cache.py` (rewrite of the parts below; same module, same class name):
   - Add `FileIdentity`:
     ```python
     @dataclass(frozen=True, slots=True)
     class FileIdentity:
         mtime_ns: int
         size: int
         inode: int
         @classmethod
         def from_stat(cls, st: os.stat_result) -> "FileIdentity": ...
         @classmethod
         def from_path(cls, path: Path) -> "FileIdentity | None": ...  # None if stat raises OSError/ValueError
     ```
   - Private `_Entry` dataclass (`model`, `identity`); store entries in `self._entries: dict[Path, _Entry]` (replaces the public `model_cache` dict of tuples).
   - `ModelCache.__init__(self, *, enabled: bool = False)`. `shared()` creates the instance disabled.
   - `enabled` property; `set_enabled(value)` sets the flag and clears entries when turning off.
   - `_get_model` returns `None` when disabled; otherwise compares the stored identity with `FileIdentity.from_path(path)` and invalidates on any difference or a failed stat. Type mismatch still invalidates and raises `ValueError`.
   - `set_model(path, model, identity: FileIdentity)` replaces the `mtime_ns: int` parameter. Disabled: no-op. Mutable model: `RuntimeError` (unchanged).
   - Delete `_check_timestamp_granularity`, `_is_cache_valid`, the `warnings`/`sys` imports and the warning.
   - Module functions:
     ```python
     def set_model_cache_enabled(value: bool) -> None: ...  # ModelCache.shared().set_enabled(value)
     def model_cache_enabled() -> bool: ...
     ```
   - Module docstring rewritten for the new contract (off by default, identity check).
2. `libs/core/kiln_ai/datamodel/basemodel.py` `load_from_file`: take `FileIdentity.from_stat(os.fstat(file.fileno()))` from the open descriptor and pass it to `set_model`.
3. `libs/core/kiln_ai/datamodel/__init__.py`: re-export `set_model_cache_enabled` and `model_cache_enabled` and list them in `__all__`.
4. Hosts:
   - `app/desktop/desktop_server.py` `lifespan`: save `model_cache_enabled()`, call `set_model_cache_enabled(True)`, restore in the innermost `finally` next to strict mode.
   - `libs/server/kiln_server/server.py`: add `default_lifespan` (async context manager: save, enable, restore). `make_app` uses it when `lifespan is None`; a caller-supplied lifespan replaces it. Short docstring on `make_app` saying so.
   - `libs/server/kiln_server/mcp/mcp.py` `main`: call `set_model_cache_enabled(True)` before `asyncio.run(...)`, next to `logging.basicConfig`.
5. Root `conftest.py`:
   - Autouse `reset_model_cache`: sets `ModelCache._shared_instance = None` before and after each test, only if `kiln_ai.datamodel.model_cache` is already in `sys.modules` (avoids importing `kiln_ai.datamodel`, which takes over a second, for test runs that never use it).
   - `model_cache_enabled` fixture: installs a fresh `ModelCache(enabled=True)` as the shared instance, yields it, restores the previous instance.
6. Existing tests that force the cache on switch to the root fixture:
   - `libs/core/kiln_ai/datamodel/test_basemodel.py`: delete the local `tmp_model_cache` and `model_cache_enabled` fixtures; tests that used `tmp_model_cache` take `model_cache_enabled`.
   - `libs/core/kiln_ai/cli/commands/test_migrate_eval_runs.py`: delete `live_model_cache`; its tests take `model_cache_enabled`. Where a test tampers with a file and relies on the cache still serving the old parse to be non-vacuous, the tamper keeps size and file id too (in-place rewrite of equal length, mtime restored).
7. Comments that describe the old check become accurate: `migrate_eval_runs.py` (`_still_matches` docstring, "validates on mtime alone") and `adapters/eval/trace_index.py` ("validates on path + mtime").
8. `.github/workflows/build_and_test.yml`:
   - `on:` gains `release: types: [created]` and `workflow_dispatch`.
   - `build` gains `if: github.event_name != 'release'`.
   - New job `test_macos_windows` with `if: github.event_name == 'release' || github.event_name == 'workflow_dispatch'`, matrix `os: [macos-latest, windows-latest]`, `fail-fast: false`, `defaults.run.shell: bash`, `env.UV_PYTHON: "3.13"`. Steps: checkout, setup-uv, `uv python install 3.13`, `uv sync --all-extras --dev`, mock web UI build dir, `uv run python -m pytest --runslow .`.
   - The Windows path-handling job is unchanged.

## Tests

`libs/core/kiln_ai/datamodel/test_model_cache.py` (rewritten; skip guards and the granularity tests deleted; each test builds its own `ModelCache(enabled=True)` unless it tests the default):
- `test_disabled_by_default`: `ModelCache()` and `ModelCache.shared()` start disabled; `set_model` stores nothing and `get_model` returns `None`.
- `test_set_enabled_false_clears`: turning off drops entries; turning back on doesn't bring them back.
- `test_set_enabled_true_on_enabled_cache_keeps_entries`
- `test_set_model_cache_enabled_switch`: the module functions read and write the shared instance.
- `test_hit_returns_same_instance_readonly_and_copy_mutable`: readonly hit is the cached instance; mutable hit is an editable copy, and editing it doesn't change the cached record.
- `test_get_model_id_returns_cached_id`, and `None` after the file changes.
- `test_changed_mtime_invalidates`: only the modified time differs.
- `test_changed_size_invalidates`: content of a different length, modified time restored.
- `test_replaced_file_new_inode_invalidates`: same-size file swapped in with `os.replace`, modified time restored with `os.utime`, so only the file id differs.
- `test_deleted_file_invalidates`
- `test_wrong_type_raises_and_invalidates`
- `test_invalidate_model`, `test_clear_cache`
- `test_cache_mutable_model_raises_error`
- `test_file_identity_from_path_missing_file_is_none`
- `test_concurrent_access_from_threads_does_not_raise`: kept, using identities.
- `test_benchmark_get_model`: kept; a hit must exceed 25k operations per second.

`libs/core/kiln_ai/datamodel/test_basemodel.py`:
- `test_load_from_file_stores_identity`: a readonly load passes `set_model` the identity of the file it read, equal to `FileIdentity.from_path`.
- `test_readonly_loads_are_not_cached_by_default`: with no fixture, two readonly loads return different instances.
- `test_readonly_loads_are_cached_when_enabled`: with the fixture, two readonly loads return the same instance, and an edit to the file on disk gives a fresh instance.

Hosts:
- `app/desktop/studio_server/test_server.py`: `test_lifespan_enables_model_cache_and_restores_it` (off before, on inside `TestClient`, off after). The existing `client` fixture is split into `app` and `client` so the new test can drive the lifespan itself.
- `libs/server/kiln_server/test_server.py` (new): `test_default_lifespan_enables_model_cache_and_restores_it` on the module-level `app` the `kiln_server` script serves; `test_caller_lifespan_replaces_default`.
- `libs/server/kiln_server/mcp/test_mcp_server.py`: `test_main_enables_model_cache_before_serving` (records `model_cache_enabled()` from inside a mocked `_async_main`).
