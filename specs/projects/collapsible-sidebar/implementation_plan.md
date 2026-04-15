---
status: complete
---

# Implementation Plan: Collapsible Sidebar

## Phases

- [x] Phase 1: Foundation stores — add `viewport.ts` + `chat_ui_state.ts`, migrate `chat_bar.svelte` to the shared `chatBarExpanded` store. Unit tests for both stores.
- [x] Phase 2: Sidebar rail — add `sidebar_rail.svelte` and all subcomponents (`sidebar_rail_item`, `task_chip`, `optimize_group`, `progress`, `settings`, `sidebar_rail_tooltip`), wire `showRail` conditional into `+layout.svelte`, implement rail→full slide-in animation. Includes the shared `sidebar_rail_tooltip.svelte` primitive (folded in from Phase 4 — all four rail tooltip callers shared the exact same hover/focus pattern and Float-based bubble, so consolidating now avoided four near-duplicate copies).
- [ ] Phase 3: Settings page "Update Available" header — prepend conditional section to `/settings` when `$update_info.update_result?.has_update`.
- [ ] Phase 4: Tooltip cleanup — **no-op**. The rail tooltip consolidation was completed in Phase 2 via `sidebar_rail_tooltip.svelte`. No cross-pollination with `info_tooltip.svelte` is planned (different use cases). This phase is preserved for audit history.
