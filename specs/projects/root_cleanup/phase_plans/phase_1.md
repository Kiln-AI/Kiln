---
status: complete
---

# Phase 1: Remove Tessl

## Overview

Tessl is no longer wanted in this repo. This phase removes all Tessl integration from the repo: tracked files, MCP server entry, and the managed block in `AGENTS.md`. `CLAUDE.md` is gitignored and auto-regenerated from `AGENTS.md` by `setup_claude.sh`, so no direct edit there.

This is a mechanical, config-only phase. No test changes are warranted.

## Steps

1. Delete `tessl.json` at repo root via `git rm tessl.json`.
2. Delete the `.tessl/` directory (only `.gitignore` is tracked) via `git rm -r .tessl`.
3. Delete `.cursor/rules/.gitignore` (existed only to ignore `tessl__*.mdc`) via `git rm .cursor/rules/.gitignore`.
4. Edit `AGENTS.md` to remove the final block (lines 67–69):

   ```
   # Agent Rules <!-- tessl-managed -->

   @.tessl/RULES.md follow the [instructions](.tessl/RULES.md)
   ```

   Also trim the trailing blank line before that block so the file ends cleanly after the "call me 'boss'" line.

5. Edit `.cursor/mcp.json` to remove the `"tessl"` entry under `mcpServers`, leaving only `HooksMCP`.

6. Verify no straggler Tessl references remain in tracked files other than this project's own spec docs (which describe the removal).

## Tests

No tests written — this is a config/file-removal phase with no runtime logic. Validation is:

- `uv run ./checks.sh --agent-mode` passes.
- `rg -i tessl` returns hits only from this project's spec docs under `specs/projects/root_cleanup/` (and possibly `.git/` / generated `CLAUDE.md` if present, both ignored).
- `.cursor/mcp.json` remains valid JSON with the `HooksMCP` entry intact.
