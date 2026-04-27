---
status: complete
---

# Phase 5: Delete `.cursor/rules/project.mdc`

## Overview

Remove the last remaining file under `.cursor/rules/`, a stale Cursor-specific rules file whose content is now authoritatively maintained in root `AGENTS.md`. With Tessl removed in Phase 1 and no other `.cursor/rules/` entries tracked, deleting this file also eliminates the `.cursor/rules/` directory itself — Cursor picks up rules from `AGENTS.md` automatically, so no agent-behavior regression is expected. This is a pure deletion with no code rewiring.

## Steps

1. `git rm .cursor/rules/project.mdc` — the directory is now empty and disappears from the working tree; run `uv run ./checks.sh --agent-mode` to confirm nothing regresses.

## Tests

No new automated tests — this phase is a pure file deletion. Automated checks verify nothing regressed; the manual validation (Cursor picks up root `AGENTS.md`) is performed out-of-band by the user.
