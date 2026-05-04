---
status: complete
---

# Implementation Plan: Multiturn Tasks

Backend lands first (phases 1–2), then frontend (phases 3–4). Each phase is independently reviewable and testable.

## Phases

- [x] **Phase 1 — Task data model + validation.** Add `TurnMode` enum, `Task.turn_mode` field with default. Add `@model_validator(mode="after")` rejecting `multiturn + input_json_schema` and `multiturn + output_json_schema` (loud `ValueError`s). Enforce immutability in `task_api.py update_task`. Backend pytest coverage for the model defaults, migration of existing task JSON without the field, forbidden combinations, and the immutability check.

- [x] **Phase 2 — Run plumbing + leaf filters.** Add `parent_task_run_id` to `RunTaskRequest`. Wire it through `run_task` (load parent run, pass `prior_trace` + `parent_task_run` to the adapter; reject single-turn + parent_task_run_id with 400; missing parent → 404). Add leaf-only filtering to `get_runs_summary` and `DatasetSplit.build_split_contents`. Backend pytest coverage for the run continuation flow, validation errors, and both leaf filters.

- [ ] **Phase 3 — Task creation/edit form.** Add `turn_mode` segmented control to `edit_task.svelte`, hide input/output schema sections when multiturn, render read-only on the edit page. Regenerate the OpenAPI client types. Frontend tests for the toggle behavior and conditional rendering.

- [ ] **Phase 4 — Multiturn run flow + conversation view.** Branch `/run/+page.svelte` on send-success to navigate to the run-detail page for multiturn tasks. Build `ConversationView`, `TurnCard`, `Composer` under `lib/ui/conversation/`. Branch the dataset run-detail page to render the conversation + composer for multiturn tasks. Each Send creates a new TaskRun and replaces the URL. Frontend tests for the three new components and the page-level branch.
