---
status: complete
---

# Phase 4: Move `.planning/` → `specs/projects/mcp_sessions/`

## Overview

Relocate the existing MCP sessions planning docs out of the ad-hoc `.planning/` directory and into the canonical `specs/projects/mcp_sessions/` location under the project's spec tree. After the move, `.planning/` is fully empty and can be deleted — one more top-level directory gone from the repo root.

This is a content-only change. No code, configs, or CI reference `.planning/` today (verified in the codebase findings for this cleanup project), so there is nothing to rewire. Existing numbered filenames (`01_codebase_findings.md`, `02_design_report.md`, `03_refinement_general_session_id.md`, `04_refinement_no_ephemeral_fallback.md`, `implementation_plan.md`) are preserved as-is per the phase directive — we're not reformatting them to the house spec layout.

## Steps

1. `git mv .planning/projects/mcp_sessions specs/projects/mcp_sessions` — moves all five markdown files with history intact.
2. `rm -rf .planning` — the directory is empty after the move (only contained `projects/mcp_sessions/`).
3. Grep the repo for any remaining references to `.planning/` or `.planning ` to confirm no stray links in code, configs, or docs. Expected remaining hits: only inside `specs/projects/root_cleanup/` (spec docs that describe this very cleanup).
4. Run `uv run ./checks.sh --agent-mode`. Should pass trivially since nothing code-related changed.

## Tests

No new automated tests — this phase is a pure filesystem relocation of markdown files. Automated checks verify nothing regressed.
