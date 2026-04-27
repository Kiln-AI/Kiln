---
status: complete
---

# Phase 8: Move `hooks_mcp.yaml` → `.config/hooks_mcp.yaml`

## Overview

Move the HooksMCP config file out of the repo root into `.config/` to reduce root clutter. Because `hooks_mcp/config.py:328` resolves prompt-file paths relative to the YAML's parent directory, every prompt path must be rewritten with a `../` prefix. The `.cursor/mcp.json` `HooksMCP` entry is updated to pass the new config path positionally. `CONTRIBUTING.md`'s reference link is updated.

## Steps

1. `git mv hooks_mcp.yaml .config/hooks_mcp.yaml`.
2. In `.config/hooks_mcp.yaml`, prefix every `prompt-file:` value with `../` so they resolve from `.config/`:
   - `AGENTS.md` → `../AGENTS.md`
   - `.agents/python_test_guide.md` → `../.agents/python_test_guide.md`
   - `.agents/frontend_design_guide.md` → `../.agents/frontend_design_guide.md`
   - `.agents/frontend_controls.md` → `../.agents/frontend_controls.md`
   - `.agents/tables_style.md` → `../.agents/tables_style.md`
   - `.agents/card_style.md` → `../.agents/card_style.md`
   (YAML field is `prompt-file:` in this file, not `file:`. Resolution rule from `hooks_mcp/config.py:328` applies to all of them — `Prompt.from_dict(..., config_dir)`.)
3. Edit `.cursor/mcp.json` `HooksMCP.args`:
   - Before: `["hooks-mcp", "--working-directory", "."]`
   - After: `["hooks-mcp", ".config/hooks_mcp.yaml", "--working-directory", "."]`
4. Edit `CONTRIBUTING.md` line 109 link target: `./hooks_mcp.yaml` → `./.config/hooks_mcp.yaml`.
5. Verify no other references to `hooks_mcp.yaml` remain in tracked (non-spec) files.
6. Run `uv run ./checks.sh --agent-mode`.

## Tests

- Config-only change; no unit tests added.
- Automated: `uv run ./checks.sh --agent-mode` passes (lint, format, types, python tests, web lint/check/test, schema check).
- Manual (out of agent's scope): restart Cursor, confirm HooksMCP tool list populates and one prompt loads.
