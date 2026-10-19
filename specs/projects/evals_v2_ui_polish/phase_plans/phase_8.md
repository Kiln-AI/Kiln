---
status: complete
---

# Phase 8 — Deterministic Forms II

## Overview

Redesign the three remaining deterministic eval forms (`set_check`, `tool_call_check`,
`step_count_check`) using the shared `form_parts` components established in Phase 7
(`form_section`, `disclosure_radio_group`, `output_value_field`). Same principles: section
structure, progressive disclosure replacing nested radios, better labels/subtitles/tooltips.

Each form's `getProperties()` and `validate()` contract is preserved exactly (same return shapes,
same validation messages, same pass/fail conditions). On-blur checks in `step_count_check` are
preserved exactly.

## Steps

1. **Redesign `set_check_form.svelte`.**
   - Replace nested radio-with-inputs with `DisclosureRadioGroup` + conditional inputs.
   - "Expected Set" section: disclosure (Fixed set via TagInput | Reference data key).
   - "Comparison Mode" section: `DisclosureRadioGroup` (equal/subset/superset with plain
     descriptions), replacing the `<select>`.
   - "Output Value to Compare" section via shared `OutputValueField`.
   - Preserve: `getProperties()` nulls inactive branch; `validate()` checks empty set / missing
     reference key; `source` init from existing props; tag sync.

2. **Redesign `tool_call_check_form.svelte`.**
   - "Match Mode" section: `DisclosureRadioGroup` (any/all/ordered/never with descriptions),
     replacing the `<select>`.
   - "On Unexpected Tools" section: `DisclosureRadioGroup` (ignore/fail), hidden when
     `match_mode === "never"` (per prior phase logic, preserved exactly).
   - "Expected Tools" section: keeps `FormList` + `Collapse` for args (complex nested structure
     unchanged in data handling). Better labels/descriptions via `FormSection`.
   - Preserve: `getProperties()` calls `sync_args_to_properties()` then returns; `validate()`
     checks empty tools and empty tool names.

3. **Redesign `step_count_check_form.svelte`.**
   - "What to Count" section: `DisclosureRadioGroup` (tool_calls/model_responses/turns with
     plain-language descriptions), replacing the `<select>`.
   - "Bounds" section: min/max number inputs with on-blur validation preserved exactly (same
     `bounds_error`, `bounds_touched`, `check_bounds`, `on_bounds_blur` logic).
   - Preserve: `getProperties()` returns properties directly; `validate()` checks at-least-one
     + min<=max; on-blur `check_bounds` reactive statement.

4. **Write tests** for all three redesigned forms covering:
   - getProperties() shape for representative inputs.
   - validate() pass/fail for the same cases as today.
   - Progressive disclosure: correct section/radio rendering.
   - Section structure with testids.
   - SetCheck: OutputValueField with Jinja tooltip.
   - ToolCallCheck: on_unexpected_tools hidden when match_mode=never.
   - StepCountCheck: getProperties returns correct count_type.

5. **Run checks** (lint, format, typecheck, tests, build) via HooksMCP tools.

## Tests

- SetCheck: validate error on empty set; validate null on populated set; validate error on
  missing reference_key; getProperties sends mode; source switching clears inactive; radio group
  renders; tag input renders for fixed source; OutputValueField label + Jinja tooltip.
- ToolCallCheck: validate error on empty tools; validate error on empty tool name; validate null
  on valid tool; getProperties returns match_mode; on_unexpected_tools hidden when never.
- StepCountCheck: validate error on no bounds; validate error on min>max; validate null on valid;
  getProperties returns count_type; radio group renders with descriptions.
- All existing contract tests in deterministic_forms.test.ts continue to pass unmodified.

## Contract preservation

- **set_check**: `getProperties()` nulls `expected_set` when source=reference_key, nulls
  `reference_key` when source=expected_set. `validate()` checks source-dependent emptiness.
- **tool_call_check**: `getProperties()` calls `sync_args_to_properties()` then returns.
  `validate()` checks >=1 tool and all names non-empty.
- **step_count_check**: `getProperties()` returns properties directly. `validate()` checks
  at-least-one-bound and min<=max. On-blur `check_bounds` preserved with same reactive pattern.
