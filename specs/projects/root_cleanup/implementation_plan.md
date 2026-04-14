---
status: complete
---

# Implementation Plan: Root Cleanup

Several small phases, each independently reviewable. Each ends with `uv run ./checks.sh --agent-mode` **plus** the phase-specific manual validation step(s).

Phases are ordered by risk (low → high) and by what unblocks later phases (e.g., `.config/` skeleton is established first, then things move into it).

## Phases

- [x] **Phase 1: Remove Tessl**
  - Delete `tessl.json`, `.tessl/`, `.cursor/rules/.gitignore`.
  - Edit `AGENTS.md` (remove `tessl-managed` block).
  - Edit `.cursor/mcp.json` (remove `tessl` MCP server entry).
  - **Manual validation:** run `rg -i tessl` and confirm only spec-doc hits remain; restart Cursor and confirm no tessl-related errors.

- [x] **Phase 2: Inline `.coveragerc` and `pytest.ini` into `pyproject.toml`**
  - Add `[tool.coverage.run]` to `pyproject.toml`; delete `.coveragerc`.
  - Merge `pytest.ini` into `[tool.pytest.ini_options]`; delete `pytest.ini`.
  - **Manual validation:** run `uv run pytest --collect-only` and diff the test count against a pre-phase capture; run `uv run coverage run -m pytest && uv run coverage report` locally and confirm output matches pre-phase omits.

- [x] **Phase 3: Move `utils/` → `.config/utils/`**
  - `git mv utils/ .config/utils/` (except `setup_claude.sh` — see Phase 7).
  - Fix `PROJECT_ROOT` in `setup_env.sh`.
  - Update refs: `CONTRIBUTING.md:69`, `.config/wt.toml:3`, `.config/wt/README.md:7`.
  - **Manual validation:** run `.config/utils/setup_env.sh` end-to-end in this worktree; confirm it completes without errors and `PROJECT_ROOT` resolves correctly (add a temporary `echo` if needed, then remove).

- [x] **Phase 4: Move `.planning/` → `specs/projects/mcp_sessions/`**
  - `git mv .planning/projects/mcp_sessions specs/projects/mcp_sessions`.
  - Delete `.planning/` (empty after move).
  - **Manual validation:** none beyond checks — content only; no code affected.

- [x] **Phase 5: Delete `.cursor/rules/project.mdc`**
  - `git rm .cursor/rules/project.mdc`.
  - **Manual validation:** open Cursor in this worktree; confirm agent picks up rules from root `AGENTS.md` (ask it "what repo am I in?" — should reference Kiln goals/tech stack).

- [x] **Phase 6: Consolidate skills at `.agents/skills/`**
  - Create `.agents/skills/` and copy content from `.cursor/skills/`.
  - Fix 2 hardcoded path refs in `.agents/skills/kiln-check-deprecation/SKILL.md` (`.cursor/skills/...` → `.agents/skills/...`).
  - `git rm -r --cached .cursor/skills`; add `.cursor/skills/` to `.gitignore`.
  - **Manual validation:** deferred to Phase 7 (which adds the setup scripts that regenerate `.cursor/skills/`).

- [x] **Phase 7: Agent setup scripts under `.agents/`**
  - `git mv .config/utils/setup_claude.sh .agents/claude/setup.sh` (from Phase 3's output).
  - Create `.agents/cursor/setup.sh` that copies `.agents/skills/*` → `.cursor/skills/*`.
  - Update `.agents/claude/setup.sh` to copy from `.agents/skills/` instead of `.cursor/skills/`.
  - Update `.config/wt.toml` and docs to point at new setup-script paths.
  - **Manual validation:**
    - Run `.agents/claude/setup.sh`; `diff -r .agents/skills .claude/skills` → empty; confirm `CLAUDE.md` is regenerated from `AGENTS.md`.
    - Run `.agents/cursor/setup.sh`; `diff -r .agents/skills .cursor/skills` → empty.
    - Restart Cursor; confirm skills appear in the skill picker.
    - Restart Claude Code; confirm skills list populates and at least one skill (e.g., `kiln-add-model`) can be invoked.

- [ ] **Phase 8: Move `hooks_mcp.yaml` → `.config/hooks_mcp.yaml`**
  - `git mv hooks_mcp.yaml .config/hooks_mcp.yaml`.
  - Rewrite every prompt `file:` path in the YAML with `../` prefix.
  - Update `.cursor/mcp.json` args: add positional `.config/hooks_mcp.yaml` before `--working-directory`.
  - Update `CONTRIBUTING.md:109` reference link.
  - **Manual validation:**
    - Restart Cursor.
    - In a Cursor session, invoke HooksMCP tools list; confirm all ~16 actions appear (`check_all`, `lint_python`, etc.).
    - Invoke one MCP prompt (`AGENTS.md` prompt) and verify it returns the file's content.
    - Run `check_all` via MCP and confirm it executes `checks.sh` from repo root successfully.

- [ ] **Phase 9: Move `tests/assets/` → `libs/core/tests/assets/`**
  - `git mv tests/assets libs/core/tests/assets`.
  - Create `libs/core/conftest.py` with moved fixtures.
  - Create `libs/server/conftest.py` that re-exports the two factory fixtures (fall back to inline copy if the import path fails).
  - Remove moved fixtures from root `conftest.py`.
  - Remove empty `tests/` directory.
  - **Manual validation:**
    - `uv run pytest libs/core -q -n auto` passes.
    - `uv run pytest libs/server -q -n auto` passes.
    - `uv run pytest -q -n auto .` passes; test count matches pre-phase baseline.
    - `rg -n 'test_data_dir|mock_file_factory|mock_attachment_factory'` shows only the expected definitions and 9 consumer files.

- [ ] **Phase 10: Move `guides/` → `.config/legacy_guides/`**
  - `git mv guides .config/legacy_guides`.
  - Delete `.config/legacy_guides/kiln_preview.avif` (unused).
  - Update self-link inside `.config/legacy_guides/Fine Tuning LLM Models Guide.md:54`.
  - **Pause and ask user** about the `README.md:69` image URL (do not guess — see functional spec item 6). Do not merge this phase until the URL is decided with the user.
  - **Manual validation:**
    - Open the PR in GitHub and check the README image renders in the GitHub rendering of `README.md`.
    - Check the PyPI package page for the Kiln release (if applicable) once the PR merges and a release cuts — or render the README through a Markdown preview tool that mimics PyPI.
    - Confirm the updated self-link in `Fine Tuning LLM Models Guide.md` resolves on GitHub.

- [ ] **Phase 11 (manual, P2): Migrate `.coderabbit.yaml` into CodeRabbit dashboard**
  - User-driven: paste `path_filters` entries into the CodeRabbit dashboard UI for this repo.
  - After dashboard config saved, delete `.coderabbit.yaml` in a follow-up PR.
  - **Manual validation:** open a test PR that modifies a file under `app/desktop/studio_server/api_client/kiln_ai_server_client/` and confirm CodeRabbit skips reviewing it (matches pre-migration behavior).

## Success criteria (cumulative, post-all-phases)

- Root has at least 10 fewer tracked entries vs. starting state.
- `uv run ./checks.sh --agent-mode` passes.
- All CI workflows green.
- Cursor, Claude Code, VS Code, Worktrunk, HooksMCP, CodeRabbit all still work.
- README renders correctly on GitHub (and PyPI after the next release).
