---
status: complete
---

# Implementation Plan: Collapsible Sidebar

## Phases

- [x] Phase 1: Foundation stores — add `viewport.ts` + `chat_ui_state.ts`, migrate `chat_bar.svelte` to the shared `chatBarExpanded` store. Unit tests for both stores.
- [ ] Phase 2: Sidebar rail — add `sidebar_rail.svelte` and all subcomponents (`sidebar_rail_item`, `task_chip`, `optimize_group`, `progress`, `settings`), wire `isRailActive` conditional into `+layout.svelte`, implement rail→full slide-in animation. Includes visual verification of multi-line tooltip (DaisyUI vs. fallback decision).
- [ ] Phase 3: Settings page "Update Available" header — prepend conditional section to `/settings` when `$update_info.update_result?.has_update`.
- [ ] Phase 4 (contingent on Phase 2 outcome): Tooltip cleanup — if DaisyUI tooltip is kept in Phase 2, refactor `info_tooltip.svelte` so logic is shared with the rail tooltips. If Phase 2 replaced DaisyUI with a custom tooltip, skip this phase.
