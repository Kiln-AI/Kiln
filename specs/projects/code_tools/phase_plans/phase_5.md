---
status: complete
---

# Phase 5: Polish + Docs

## Overview

Final polish phase before Code Tools can ship (modulo Phase 6 trust integration). Adds worked examples to the examples dialog with matching documentation, PostHog analytics events for key actions, an empty state for the tools index, and cross-OS spawn sanity documentation. P2 items are evaluated and tracked.

## Steps

### 1. Improve examples dialog content (code_tool_helpers.ts)

The three examples already exist in `generateExamples()`. They are good but need refinement to better match the real API:

- **Parallel with Retries**: already uses `ThreadPoolExecutor` + `tools.fetch_url(...)` with `json.loads`. Good match.
- **Async Fan-Out**: already uses `async_tools.get_user(...)` + `asyncio.gather`. Good match.
- **Filter & Transform**: already uses `tools.search(...)` + `json.loads`. Good match.

All three examples properly demonstrate the real in-Python API (`from kiln import tools` / `from kiln import async_tools`), return `str` via `json.dumps`, and use `json.loads` for parsing tool results. The examples are valid Python.

No content changes needed to the examples themselves — they already match the real API accurately.

### 2. PostHog analytics events

Add `posthog.capture` calls for key code-tool actions, matching existing naming conventions:

- `test_code_tool` — fired in `code_tool_test_panel.svelte` on every completed test run (both success and error results; a `success` flag distinguishes them). Not fired on `not_trusted` (nothing executed) or user cancellation.
- `archive_code_tool` — fired in detail page on archive/unarchive
- `clone_code_tool` — fired in detail page on clone
- `delete_code_tool` — fired in detail page on delete

Note: `create_code_tool` is already captured in the create flow. The `test_code_tool` event fires client-side since the test panel is the key user interaction worth tracking.

### 3. Empty state for tools index

The tools index already has an `EmptyTools` component that shows when `is_empty`. This already includes code tools in the `is_empty` check. The existing empty state is good and covers the case.

However, the empty_tools description text could be updated to mention code tools alongside the existing tool types. Update the description to include "code tools" in the list.

### 4. Cross-OS spawn sanity documentation

Create a cross-OS spawn sanity checklist at `specs/projects/code_tools/cross_os_spawn_checklist.md`. Document:

- macOS: can run spawn sanity test locally — verify `multiprocessing.spawn` context works with `start_process_with_light_main`.
- Windows: cannot run here — document the checklist items (frozen build with PyInstaller, `freeze_support()`, `_spawn_lock` shared with code-evals).
- Linux: cannot run here — document the checklist items.
- Frozen build (PyInstaller): document that `start_process_with_light_main` stays within `multiprocessing.spawn`'s bootstrap so `freeze_support()` works; verify on each OS target in the release checklist.

Run a macOS-local spawn test via the existing test suite to confirm spawn works on this platform.

### 5. P2 items assessment

Evaluate each P2 item and decide:

- **stdout/stderr display**: The API already returns these fields. Adding collapsed sections in the test panel is relatively straightforward. Implement if clean.
- **Code copy button**: Adding a copy button on the readonly code block on the detail page. This is trivial. Implement.
- **User-facing description field**: Already partially wired — the `description` field exists on the model, the API accepts it, the detail page shows it. The create flow omits it per spec ("P2 — cut if unneeded"). Leave deferred — adding it to the create flow would need UX decisions about where it goes relative to the model-facing description. The detail page already shows it in the Notes section and the edit dialog could accept it.

## Tests

- Existing `code_tool_helpers.test.ts` tests already verify all three examples have the correct structure (labels, code content).
- PostHog events are best tested by visual inspection of the PostHog dashboard; they follow the established fire-and-forget pattern used throughout the codebase.
- No new test files needed for this phase — changes are cosmetic/analytics.
