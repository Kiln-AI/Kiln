---
status: complete
---

# Phase 7: Agent setup scripts under `.agents/`

## Overview

Move the Claude setup script from `.config/utils/setup_claude.sh` to `.agents/claude/setup.sh`, add a parallel `.agents/cursor/setup.sh`, and update both scripts to materialize `.claude/skills/` and `.cursor/skills/` from the canonical `.agents/skills/` location established in Phase 6. Update `wt.toml` and docs to point at the new paths.

After this phase, new worktrees bootstrap via `.agents/claude/setup.sh` (invoked by `wt`), and Cursor users can run `.agents/cursor/setup.sh` manually (or via any additional `wt` hook slot, if one exists) to populate `.cursor/skills/`.

## Steps

1. `git mv .config/utils/setup_claude.sh .agents/claude/setup.sh` (creating `.agents/claude/` if missing).
2. Rewrite `.agents/claude/setup.sh` to:
   - Keep `set -e` and shebang.
   - Self-locate repo root via `SCRIPT_DIR` so it works regardless of CWD: `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"; cd "$REPO_ROOT"`.
   - Copy `AGENTS.md` → `CLAUDE.md`.
   - Copy `.agents/skills/` → `.claude/skills/` (instead of the old `.cursor/skills/` source). Remove the stale destination first so the copy is a clean replacement (`rm -rf .claude/skills`).
3. Create `.agents/cursor/setup.sh` mirroring the Claude script style:
   - Shebang, `set -e`, same self-locate pattern.
   - Copy `.agents/skills/` → `.cursor/skills/` (clean replace).
   - Echo a completion message.
   - `chmod +x` after creation.
4. Update `.config/wt.toml`: change the `claude` hook value from `.config/utils/setup_claude.sh` to `.agents/claude/setup.sh`. `wt` post-create has only `deps` and `claude` slots today; no Cursor slot exists, so document `.agents/cursor/setup.sh` in `.config/wt/README.md` instead.
5. Update `.config/wt/README.md` Architecture section to mention the new agent setup scripts (`.agents/claude/setup.sh` for Claude bootstrap, `.agents/cursor/setup.sh` for Cursor skills).
6. `grep -rn setup_claude` in tracked files (excluding `specs/`) and confirm no stale references remain in code/config. Spec docs are allowed to reference the old name — they describe the migration itself.
7. Run `.agents/claude/setup.sh` and `diff -r .agents/skills .claude/skills` → must be empty. Confirm `CLAUDE.md` exists.
8. Run `.agents/cursor/setup.sh` and `diff -r .agents/skills .cursor/skills` → must be empty.
9. Run `uv run ./checks.sh --agent-mode`.

## Tests

- Config-only / script-only change: no new automated tests. Validation is via the manual post-run diff commands (step 7 and 8) plus `checks.sh`.
