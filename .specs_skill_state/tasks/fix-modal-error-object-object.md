---
status: complete
created: 2026-05-13
---

# Task: Fix "[object Object]" error rendering in project/task picker modal

## Request

We have a bug. In the modal that lets me pick project and task, errors don't render well. I get "Tasks failed to load: [object Object]", we never want that.

diagnose and fix. Don't commit until I review

## Notes

- User has explicitly requested: **do not commit** at the end of the loop — pause after CR is clean so user can review the diff.
- Bug surface: a modal in the web UI (Svelte) that lets the user pick a project and task. Error message currently rendered as `Tasks failed to load: [object Object]` — meaning the error object is being stringified raw rather than being passed through the project's error-message extraction utility.
- Scope: diagnose the error rendering issue in the project/task picker modal. Check for similar bad patterns nearby (project-load errors in the same modal, etc.) and fix them as part of the same task — but do not go on a broader hunt across unrelated UI.
- Likely root cause area: a Svelte component is doing something like `` `Tasks failed to load: ${error}` `` or `String(error)` instead of using the project's existing helper (e.g., `createKilnError(...).getMessage()` or similar). Investigate first, then fix consistently.
