---
status: complete
---

# Phase 2: Inline `.coveragerc` and `pytest.ini` into `pyproject.toml`

## Overview

Consolidate root-level test/coverage configuration into `pyproject.toml` so the root has fewer scattered config files. This phase is config-only: no code changes, no test changes. Outcome:

- `.coveragerc` contents migrated to `[tool.coverage.run]` in `pyproject.toml`, then `.coveragerc` deleted.
- `pytest.ini` contents merged into existing `[tool.pytest.ini_options]` in `pyproject.toml`, then `pytest.ini` deleted.
- Test discovery and coverage omit behavior unchanged.

Pre-phase baseline: `uv run pytest --collect-only -q` reports **12867 tests**.

## Steps

1. **Edit `pyproject.toml`**: add a new `[tool.coverage.run]` table with the same four omit entries from `.coveragerc`, converted to TOML list-of-strings form:
   ```toml
   [tool.coverage.run]
   omit = [
       "**/test_*.py",
       "libs/core/kiln_ai/adapters/ml_model_list.py",
       "conftest.py",
       "*/kiln_ai_server_client/*",
   ]
   ```

2. **Edit `pyproject.toml`**: merge `pytest.ini` contents into the existing `[tool.pytest.ini_options]` table. Current state only has `addopts="-n auto"` (commented-out in pytest.ini, so we keep it as-is in pyproject). Add:
   - `asyncio_mode = "auto"`
   - `asyncio_default_fixture_loop_scope = "function"` (unquote the INI value — in TOML the string needs one layer of quoting, no inner quotes)
   - `markers = [...]` as a list (TOML equivalent of the INI multi-line list)
   - `filterwarnings = [...]` as a list

   The commented-out `addopts = -n auto` line in pytest.ini duplicates what pyproject already has — skip the comment, keep the active `addopts`.

   **Intentional behavior shift:** `addopts = "-n auto"` was commented out in `pytest.ini` (with a "single tests faster without it" note) but is active in `pyproject.toml`. After this migration, ad-hoc `uv run pytest` invocations will run parallel by default. `checks.sh` already uses `-n auto` explicitly so CI behavior is unchanged. The stale "single tests faster" note is discarded.

3. **Delete `.coveragerc`** via `git rm .coveragerc`.

4. **Delete `pytest.ini`** via `git rm pytest.ini`.

5. **Verify**:
   - `uv run pytest --collect-only -q` still reports 12867 tests.
   - `uv run coverage run -m pytest --collect-only` parses the new config without complaint (light check — don't run full coverage here; that's the manual validation the user will do).
   - `uv run ./checks.sh --agent-mode` passes end-to-end.

## Tests

No new tests — this is a config-only migration. The regression signal is:

- Pytest collection count unchanged (12867).
- `coverage` CLI accepts `pyproject.toml` config (coverage has supported `pyproject.toml` config since 5.0 via `[tool.coverage.*]`).
- Existing test suite still passes under `checks.sh`.
