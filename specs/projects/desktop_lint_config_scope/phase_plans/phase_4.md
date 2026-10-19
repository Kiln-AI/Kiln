---
status: complete
---

# Phase 4: Flip the config

## Overview

The point of the project. Phases 1–3 cleared every finding the root ruff config would raise
under `app/desktop`, but nothing enforced them — `app/desktop/pyproject.toml` carries its own
`[tool.ruff]` section, which stops ruff's config walk before it reaches the root and so denies
that tree the repo's `extend-select = ["I","F401","RUF","FAST","TID"]` rules.

This phase deletes that section and moves its only meaningful content — the generated-client
exclude — up to the root config, re-pathed to be root-relative. After this, one ruff config
governs the whole repo and CI enforces the root rules on `app/desktop` automatically.

No CI change is needed: `checks.sh` and `.github/workflows/format_and_lint.yml` both invoke a
bare `uv run ruff check` from the repo root, with no `working-directory` override. Verified,
not assumed.

## Steps

1. **Re-run the audit before touching anything.** Any finding that landed in `app/desktop`
   mid-project gets fixed here rather than trusting phases 1–3:

   ```bash
   uv run ruff check --config pyproject.toml \
     --exclude app/desktop/studio_server/api_client/kiln_ai_server_client app/desktop
   ```

2. **`pyproject.toml` (root)** — extend the existing exclude, preserving `.worktrees` and
   carrying the explanatory comment up with the path. The path gains an `app/desktop/` prefix
   because exclude paths containing a slash resolve relative to the config file's directory:

   ```toml
   [tool.ruff]
   exclude = [
       ".worktrees",
       # Automatically generated code, so we don't lint it
       "app/desktop/studio_server/api_client/kiln_ai_server_client",
   ]
   ```

3. **`app/desktop/pyproject.toml`** — delete the entire `[tool.ruff]` section. Everything else
   in the file stays: `[build-system]`, `[project]`, `[tool.uv]`, `[tool.uv.sources]`,
   `[tool.hatch.build.targets.wheel]`.

## Tests

No new tests. This project adds no behaviour; a test asserting "the ruff config is shaped a
certain way" would be testing ruff, not Kiln. Verification is the check suite itself:

- `uv run ruff check` — bare, no `--config`, no `--exclude`. This is what CI runs. Must pass,
  and it now covers `app/desktop` under the root rules.
- **Prove the exclude actually resolved.** A pass alone is not proof; a bad exclude path would
  surface as a large finding count, not silence. Confirm the root-relative path is doing its
  job: `uv run ruff check --no-cache --statistics app/desktop` must report a clean run.
  Several hundred findings dominated by `TID252`/`TID251` means the exclude is not applying.
- `uv run ruff format --check .` — passes, and the generated client is untouched.
- `git status --porcelain app/desktop/studio_server/api_client/kiln_ai_server_client` must
  print nothing after a real `uv run ruff format .`. Output here means ruff reformatted
  generated code, i.e. the exclude did not resolve.
- `uv run python3 -m pytest --benchmark-quiet -q -n auto app/desktop` — desktop suite green.
- `uv run ./checks.sh --agent-mode` — the full suite.

## Known, out of scope

The root key is `exclude`, which *replaces* ruff's built-in default exclude list rather than
adding to it (`extend-exclude` is the extending form). This is not a regression introduced here:
the deleted `app/desktop` section had exactly the same shape, so that tree was already running
without ruff's defaults, and `respect-gitignore` covers those directories in practice. Recorded
so it is not lost; deliberately not changed as part of this project.
