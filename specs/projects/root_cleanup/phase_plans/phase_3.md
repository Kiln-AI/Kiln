---
status: complete
---

# Phase 3: Move `utils/` → `.config/utils/`

## Overview

Relocate the three root-level `utils/` scripts (`setup_env.sh`, `setup_claude.sh`, `pre-commit-hook`) into `.config/utils/` as part of the broader root cleanup. This keeps dev-bootstrap tooling under `.config/` and removes one more top-level directory from the repo root.

`setup_claude.sh` is ultimately destined for `.agents/claude/setup.sh` (Phase 7), but moving it with the rest of `utils/` now keeps the working tree consistent and leaves Phase 7 as a simple `git mv` + wt.toml edit. The script is invoked by `wt` post-create and uses only repo-root-relative paths (`AGENTS.md`, `.cursor/skills`, `.claude/`), so its on-disk location doesn't affect its behavior.

## Steps

1. `git mv utils/setup_env.sh .config/utils/setup_env.sh`
2. `git mv utils/pre-commit-hook .config/utils/pre-commit-hook`
3. `git mv utils/setup_claude.sh .config/utils/setup_claude.sh`
4. Edit `.config/utils/setup_env.sh`: change
   `PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"` →
   `PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"`
   (script is now 2 levels deep under project root).
5. Edit `CONTRIBUTING.md:69`:
   `cp utils/pre-commit-hook ...` → `cp .config/utils/pre-commit-hook ...`.
6. Edit `.config/wt.toml:3`:
   `claude = "utils/setup_claude.sh"` → `claude = ".config/utils/setup_claude.sh"`.
7. Edit `.config/wt/README.md:7`:
   `utils/setup_env.sh` → `.config/utils/setup_env.sh`.
8. Delete now-empty `utils/` directory.
9. Re-grep for any stray `utils/setup_env|utils/setup_claude|utils/pre-commit-hook` references outside the spec docs; fix any that remain.
10. Manual validation: temporarily add `echo "$PROJECT_ROOT"` in `.config/utils/setup_env.sh`, run it end-to-end (answer `N` to the workspace prompt to avoid side effects), verify the printed path matches the worktree root, then remove the echo.
11. Run `uv run ./checks.sh --agent-mode`; fix any regressions.

## Tests

No new automated tests — this phase is a file relocation + three one-line edits. Behavior is validated manually by running `setup_env.sh` and by inspection of the updated references.
