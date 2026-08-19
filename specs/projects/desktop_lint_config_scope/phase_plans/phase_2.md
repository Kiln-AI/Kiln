---
status: complete
---

# Phase 2: `I001` import sorting

## Overview

Clear all 51 `I001` unsorted-imports findings under `app/desktop/`, so that when Phase 4 flips
the ruff config the rule is already clean.

This phase is deliberately the least interesting one in the project. Every hunk in the diff is
produced by `ruff check --select I --fix` followed by `ruff format`, with no hand edits. It is
isolated into its own commit precisely so a reviewer can skim a 50-file diff knowing that if any
hunk is *not* an import-block reordering, something went wrong.

`I001` is a safe fix in ruff's classification, so bulk `--fix` is permitted here — unlike the
`RUF059` sweep in Phase 1, which was unsafe and hand-edited.

## Site survey

51 findings across 50 files. `studio_server/test_data_gen_api.py` carries two (two separate
import blocks in one file); every other file carries one.

| Area | Files |
|---|---|
| `studio_server/` (top level) | 23 |
| `studio_server/chat/` | 8 |
| `studio_server/utils/` | 4 |
| `studio_server/jobs/` | 3 |
| `studio_server/api_client/` | 2 |
| `studio_server/api_models/` | 1 |
| `git_sync/integration_tests/` | 6 |
| `git_sync/` (top level) | 2 |
| `dev_server.py` | 1 |

No file under `studio_server/api_client/kiln_ai_server_client` may appear in the diff — that is
the generated client, and its presence would mean the audit command was run without `--exclude`.

### The two files that change import-statement grouping

48 of the 50 files change only the order of import statements and their blank-line group
separators. Exactly two change the grouping itself, and they are the only places a reviewer needs
to look for something other than a reordering:

- **`git_sync/git_sync_api.py`** — the `kiln_ai.utils.project_utils` block *splits into two*
  statements, isolating `project_from_id as project_from_id_core`. This is ruff/isort's default
  `combine-as-imports = false` behaviour; the repo sets no isort config, so the default applies.
  It matches existing repo style — `libs/server/kiln_server/project_api.py:8-15` has the identical
  shape at HEAD, same module and same alias.
- **`studio_server/chat/test_stream_session.py`** — two separate
  `app.desktop.studio_server.chat.stream_session` blocks *merge into one*. Same module either way,
  so module initialization order is unaffected.

Both are binding-identical; only the statement count changes.

## Steps

1. Apply the safe autofix, forcing the root config and preserving the generated-client exclude:

   ```bash
   uv run ruff check --config pyproject.toml \
     --exclude app/desktop/studio_server/api_client/kiln_ai_server_client \
     --select I --fix app/desktop
   ```

   No `--unsafe-fixes`. No hand edits.

2. Re-run `uv run ruff format .` — reordering imports can change how a block wraps, and the
   formatter is the authority on that.

3. Read the diff. Confirm every hunk is confined to an import block: lines moved or regrouped,
   none added, none removed, no non-import line touched. `git diff --stat` should show a roughly
   symmetric insertion/deletion count per file.

   Because the reviewable claim is "nothing but reordering", check it mechanically rather than by
   eye — parse each changed file and compare it against `HEAD` for an identical multiset of import
   bindings (module, level, name, asname, at every block level including function-local imports)
   and a byte-identical AST with all imports stripped. Counting import *statements* the same way
   isolates the two grouping changes noted above.

4. Confirm nothing under `studio_server/api_client/kiln_ai_server_client` was modified:

   ```bash
   git status --porcelain app/desktop/studio_server/api_client/kiln_ai_server_client
   ```

   Must print nothing.

## Tests

No new tests. This phase adds no behaviour; it reorders import statements. The functional spec
and architecture both record that a test asserting "imports are sorted" would be testing ruff.

The existing desktop suite is the safety net, and it is a real one here: import reordering can
change module initialization order and expose an import cycle or a monkeypatch that depended on
binding order. Verification per the architecture doc:

- `uv run ruff check --config pyproject.toml --exclude app/desktop/studio_server/api_client/kiln_ai_server_client --select I app/desktop` — zero findings.
- `uv run ruff check --config pyproject.toml --exclude app/desktop/studio_server/api_client/kiln_ai_server_client --statistics app/desktop` — the remaining count drops from 73 to 22, and `I001` is gone from the table.
- `uv run ruff format --check .` — clean.
- `uv run python3 -m pytest --benchmark-quiet -q -n auto app/desktop` — full desktop suite passes.
- `uv run ./checks.sh --agent-mode` — the whole repo still passes, since plain `ruff check` and
  the rest of CI must stay green at every commit in this project.
