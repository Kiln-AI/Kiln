---
status: draft
---

# Phase 6: Rebase Phase 4 Annotations onto API Docs Overhaul

## Overview

The `scosman/improve-api-docs` branch overhauled most API endpoints (docs, paths, signatures), creating hundreds of conflicts with Phase 4's annotation backfill. Rather than resolving merge conflicts line-by-line, we revert Phase 4, merge the docs branch, and re-apply the annotation logic using the Phase 4 diff as a guide.

## Steps

1. **Get the list of API files changed in Phase 4**
   - `git diff --name-only 810eb683d^..810eb683d` to get the full file list.
   - This is the checklist for re-application. Track which files have been covered.

2. **Revert the Phase 4 commit**
   - `git revert 810eb683d --no-edit`
   - This cleanly removes all Phase 4 annotation changes and regenerated JSONs.

3. **Merge `scosman/improve-api-docs` into this branch**
   - `git merge origin/scosman/improve-api-docs`
   - Resolve any conflicts (should be minimal since Phase 4 is reverted).

4. **Re-apply annotations file-by-file**
   - For each API file from step 1, use `git diff 810eb683d^..810eb683d -- <file>` to see exactly what Phase 4 did to that file.
   - Read the current version of the file (post-merge) and apply the same annotation logic:
     - Add the `openapi_extra=` parameter with the correct policy constant/constructor.
     - Handle moved/renamed/split endpoints by matching on the endpoint's purpose, not its old path.
   - Follow the same default rules as Phase 4:
     - GET → `ALLOW_AGENT`
     - POST → `ALLOW_AGENT`
     - DELETE → `DENY_AGENT`
     - PATCH → `agent_policy_require_approval("Allow agent to edit [resource]? ...")`
   - Apply the same special-case overrides (settings→DENY, filesystem→DENY, cost APIs→require_approval, etc.)
   - Any **new** endpoints introduced by the docs branch should also be annotated following the defaults.
   - After all files are done, compare the covered file list against step 1 to confirm nothing was missed.

5. **Regenerate annotation JSONs**
   - Run the dump CLI against the live server to regenerate all annotation JSONs.
   - Verify exit code 0 (all endpoints annotated).

6. **Run automated checks**
   - Lint, format, type check, tests. Iterate until clean.

## Tests

- No new test files — this phase is a re-application of existing logic.
- Verify all existing tests pass (Phase 1-3 tests still green).
- Verify dump CLI exits 0 (no unannotated endpoints).
