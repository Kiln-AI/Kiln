---
status: complete
---

# Implementation Plan: Input Transformer UI

Frontend-only (`app/web_ui`), read-only. See `functional_spec.md` and `architecture.md` for details.

## Phases

- [x] **Phase 1 — Core: types, helpers, modal, details row.**
  Add the `JinjaInputTransform` / `InputTransform` type aliases (§Arch 1); the `getInputTransformDisplay`, `getRunConfigInputTransform`, `getRunConfigInputTransformSummaryLabel` helpers with exhaustive `never` guards (§Arch 2); the `input_transform_modal.svelte` component (§Arch 3); the new `action?` field on `UiProperty`/`PropertyList` plus the "Input Transformer" row + callback/modal wiring on all three `getRunConfigUiProperties` consumer pages (§Arch 4). Unit + component tests (§Arch 7, minus the summary-surface assertions).

- [ ] **Phase 2 — Summary surfaces.**
  Add the "Input Transform: Custom" indicator (only-when-present) to: selector dropdown, compare column headers, `RunConfigSummary` card, both comparison charts (legend + tooltip), and the optimize-page table badge (§Arch 5). Tests for the summary helper coverage.
