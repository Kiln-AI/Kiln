---
status: complete
---

# Implementation Plan: Multiturn Trace Forking

## Phases

- [x] **Phase 1: Backend — ancestors endpoint.** Add `TaskRunAncestor` / `TaskRunAncestorsResponse` models, `_walk_ancestors` and `_count_user_messages` helpers, `GET .../runs/{run_id}/ancestors` route with cycle/depth/length-mismatch handling. Cover with the 7 pytest cases in `test_run_api.py`. Regenerate OpenAPI schema so the frontend types pick up the new endpoint. See `architecture.md` → Backend section.

- [x] **Phase 2: Frontend — fork UI.** Extract the inline append composer into `MultiturnComposer.svelte` (append mode only, no behavior change). Add fork mode (context strip, prefill, run config seed, Cancel + dirty-confirm dialog). Add `ForkIcon.svelte`. Extend `trace.svelte` with `forkable_run_ids` / `truncate_at_trace_index` / `on_fork` props. Wire it all together in the run-detail `+page.svelte`: ancestors fetch, `compute_forkable_run_ids`, fork-target state, banners for `chain_broken` and load-failure, navigation on send. Vitest coverage per `architecture.md` → Testing Strategy. See `architecture.md` → Frontend section.
