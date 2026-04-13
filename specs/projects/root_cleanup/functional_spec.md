---
status: complete
---

# Functional Spec: Root Cleanup

This doc describes what each move looks like in detail: before/after, reference updates, and success criteria. Execution order is deferred to `implementation_plan.md`.

---

## 1. Remove Tessl

**Rationale:** Tessl is no longer wanted in this repo.

**Delete:**
- `tessl.json` (root)
- `.tessl/` (folder + contents; `.tessl/.gitignore` is the only tracked file, plus generated `RULES.md` / `tiles/`)
- `.cursor/rules/.gitignore` (it existed solely to ignore `tessl__*.mdc`)

**Edit:**
- `AGENTS.md` — remove the `# Agent Rules <!-- tessl-managed -->` block (current lines 67–69).
- `.cursor/mcp.json` — remove the `"tessl"` entry from `mcpServers`.
- `CLAUDE.md` — ignore; it's generated from `AGENTS.md` by `setup_claude.sh`, so it fixes itself on the next run.

**Success:** `grep -ri tessl .` returns no matches (other than in this spec doc and git history).

---

## 2. `utils/` → `.config/utils/`

**Move:** all three files (`setup_env.sh`, `setup_claude.sh`, `pre-commit-hook`) from `utils/` to `.config/utils/`. (Note: `setup_claude.sh` moves separately in item 10 below — see caveat.)

**Edit:**
- `CONTRIBUTING.md:69` — `cp utils/pre-commit-hook ...` → `cp .config/utils/pre-commit-hook ...`.
- `.config/wt.toml:3` — `claude = "utils/setup_claude.sh"` → new path (see item 10).
- `.config/wt/README.md:7` — path to `setup_env.sh`.
- `.config/utils/setup_env.sh` — fix `PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"` → `PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"` (now 2 levels deep, not 1).

**Success:** `utils/` no longer exists; dev bootstrap still works (`.config/utils/setup_env.sh` runs to completion on a clean checkout).

---

## 3. `.coveragerc` → `pyproject.toml`

**Delete:** `.coveragerc` (root).

**Edit:** `pyproject.toml` — add `[tool.coverage.run] omit = [...]` with the same four entries.

**Verify:** `.github/workflows/coverage.yml` invocations still produce non-empty `coverage report` with the same omits.

**Success:** coverage produces identical output; no `--rcfile` flag needed.

---

## 4. `pytest.ini` → `pyproject.toml`

**Delete:** `pytest.ini` (root).

**Edit:** `pyproject.toml` — merge the INI contents into `[tool.pytest.ini_options]` (already exists in most pyproject layouts; inspect and merge cleanly).

**Verify:** `uv run pytest --collect-only` discovers the same tests; `uv run pytest -q -n auto .` passes.

**Success:** `pytest.ini` gone; all tests discovered and passing.

---

## 5. `.planning/` → `specs/projects/mcp_sessions/`

**Move:** `.planning/projects/mcp_sessions/*` → `specs/projects/mcp_sessions/`.

**Delete:** `.planning/` directory.

**Content format:** keep the numbered stage filenames as-is (`01_codebase_findings.md`, etc.). No rewrite to the `architecture.md` / `functional_spec.md` layout — this is legacy content, and conversion adds churn without benefit.

**Success:** `.planning/` gone; `ls specs/projects/mcp_sessions/` shows the five markdown files.

---

## 6. `guides/` → `.config/legacy_guides/`

**Move:** entire `guides/` folder → `.config/legacy_guides/`.

**Delete:** `guides/kiln_preview.avif` (unused, 3.5 MB).

**Edit:**
- `README.md:69` — `<img src="guides/kiln_preview.gif">` → **manual:** work with user to pick the right URL (needs to render on GitHub and PyPI; current README uses `https://github.com/user-attachments/...` style for other images at lines 61, 75 — may want to upload to user-attachments rather than link into `.config/legacy_guides/`). Do NOT guess; pause and ask.
- `.config/legacy_guides/Fine Tuning LLM Models Guide.md:54` — absolute GitHub URL updated to new path.

**Accept:** external inbound links to the old `github.com/Kiln-AI/Kiln/blob/main/guides/...` URLs will 404. This is explicitly accepted by the user.

**Success:** `guides/` gone; README image renders in GitHub and on PyPI.

---

## 7. `.cursor/rules/project.mdc` — delete

**Delete:** `.cursor/rules/project.mdc` (stale, abbreviated duplicate of `AGENTS.md`; Cursor reads root `AGENTS.md` natively per https://cursor.com/docs/context/rules).

**Success:** file gone; Cursor sessions still pick up project rules (via root `AGENTS.md`).

---

## 8. `.cursor/skills/` → `.agents/skills/` (central canonical location)

**Move tracked content:** `.cursor/skills/*` → `.agents/skills/`. (Byte-identical to `.claude/skills/*` today, but `.claude/` is already gitignored, so only the Cursor copy is tracked.)

**Edit:**
- `.agents/skills/kiln-check-deprecation/SKILL.md` — fix 2 hardcoded path refs that currently point at `.cursor/skills/kiln-check-deprecation/scripts/...` → `.agents/skills/kiln-check-deprecation/scripts/...`.

**Gitignore:** add `.cursor/skills/` (becomes a setup-script artifact, parallel to how `.claude/` is handled today).

**Runtime bridging:** setup scripts (item 10) materialize `.cursor/skills/` and `.claude/skills/` from `.agents/skills/` at dev-setup time. Copy, not symlink — consistent with the user's stance on `CLAUDE.md` (no symlinks; setup script + gitignore).

**Success:** `.cursor/skills/` removed from git tracking; one source of truth at `.agents/skills/`; Cursor and Claude Code both still see their skills after setup.

---

## 9. `hooks_mcp.yaml` → `.config/hooks_mcp.yaml`

**Move:** `hooks_mcp.yaml` → `.config/hooks_mcp.yaml`.

**Edit:**
- `.cursor/mcp.json` — update the `HooksMCP` entry's args to `["hooks-mcp", ".config/hooks_mcp.yaml", "--working-directory", "."]` (positional config path; `hooks-mcp` already accepts this per the `hooks_mcp` project at `/Users/scosman/Dropbox/workspace/misc/actions_mcp/hooks_mcp`).
- `.config/hooks_mcp.yaml` — rewrite prompt paths so they resolve correctly. Options: (a) use paths relative to the config dir (`../AGENTS.md`, `../.agents/...`), or (b) verify `hooks-mcp` honors `--working-directory` for prompt resolution and use repo-root-relative paths. Pick (a) unless a smoke test confirms (b) works — (a) is a mechanical transformation; (b) requires code-reading the tool.
- `CONTRIBUTING.md:109` — update the reference link.

**Smoke test:** start a Cursor session; confirm HooksMCP tools list populates and one prompt (e.g., `AGENTS.md`) loads correctly.

**Success:** `hooks_mcp.yaml` gone from root; MCP tools and prompts work in Cursor.

---

## 10. Setup scripts: agent-scoped under `.agents/`

**Move/rename:**
- `utils/setup_claude.sh` → `.agents/claude/setup.sh` (agent-specific, belongs with other Claude agent config).
- `utils/setup_env.sh` → `.config/utils/setup_env.sh` (stays as a general dev bootstrap, per item 2; not agent-specific).
- `utils/pre-commit-hook` → `.config/utils/pre-commit-hook` (per item 2).

**Add:**
- `.agents/cursor/setup.sh` — materializes `.cursor/skills/` from `.agents/skills/` (copy, consistent with the Claude pattern).

**Edit:**
- `.agents/claude/setup.sh` — update to copy `AGENTS.md` → `CLAUDE.md` (already does) and copy `.agents/skills/*` → `.claude/skills/` (was `.cursor/skills/` → `.claude/skills/`).
- `.config/wt.toml:3` — point `claude = ".agents/claude/setup.sh"` (was `utils/setup_claude.sh`).
- `.config/wt.toml` — add a parallel entry for Cursor if `wt` has a Cursor-setup slot (otherwise document it in `.config/wt/README.md`).
- `CONTRIBUTING.md` — update any refs.

**Success:** new worktrees bootstrap via `.agents/claude/setup.sh` (or `.agents/cursor/setup.sh`) and produce working `CLAUDE.md`, `.claude/skills/`, `.cursor/skills/` with no tracked duplication.

---

## 11. `tests/assets/` → `libs/core/tests/assets/`

**Move:** all 15 files (14 assets + `README.md`) from `tests/assets/` → `libs/core/tests/assets/`.

**Edit `conftest.py`:**
- Remove `MockFileFactoryMimeType`, `test_data_dir`, `mock_file_factory`, `mock_attachment_factory` from the root `conftest.py`.
- Create `libs/core/conftest.py` containing these fixtures, with `test_data_dir = Path(__file__).parent / "tests" / "assets"`.
- Create a minimal `libs/server/conftest.py` that re-exports `mock_file_factory` / `mock_attachment_factory` from `libs.core.conftest` (or equivalent import path) so `libs/server/kiln_server/test_document_api.py` keeps working. If simpler, inline a small duplicate for the one consumer.

**Delete:** top-level `tests/` directory (empty after the move).

**Verify:** `uv run pytest libs/core libs/server -q` passes; test count unchanged.

**Success:** `tests/` gone; asset ownership matches consumption.

---

## 12. `.coderabbit.yaml` — P2, manual

**Defer.** Last phase. User migrates path filter into the CodeRabbit dashboard UI manually, then deletes `.coderabbit.yaml`. Not automated; not blocked by other phases.

---

## Success criteria (overall)

- Repo root file/folder count reduced by at least 10 entries.
- `uv run ./checks.sh --agent-mode` passes on the final phase.
- `.github/workflows/*` run green without edits beyond the moves described above.
- VS Code, Cursor, Claude Code, Worktrunk all still work without user-level config changes.
- README renders correctly on GitHub and PyPI.

## `.config/` target structure

After all moves, `.config/` holds:

```
.config/
├── hooks_mcp.yaml       # moved from root (item 9)
├── legacy_guides/       # moved from root/guides (item 6)
├── utils/               # moved from root/utils (item 2) — setup_env.sh, pre-commit-hook
├── wk.yml               # existing (worktrunk-adjacent)
├── wt.toml              # existing (worktrunk)
└── wt/                  # existing (worktrunk settings)
```

Kept flat rather than nested deeper — items are heterogeneous but the count is low enough that subgrouping adds noise. If `.config/` ever exceeds ~10 top-level entries, revisit.

## Explicit non-goals

- No rewriting or reformatting of content that's merely being moved.
- No changes to the public Kiln API, CLI, or Python package.
- No changes to `.github/`, `.env`, `checks.sh`, `Makefile`, `conftest.py` (other than the fixture move in item 11), `pyproject.toml` (other than additions in items 3 and 4).
