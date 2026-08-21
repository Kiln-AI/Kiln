---
status: complete
---

# Phase 4: Deterministic form correctness + picker

## Overview

Hardens deterministic eval-type forms with backend model fixes, wording corrections, validation,
and conditional UI. Makes `set_check.mode` a required field (no silent default), fixes "JSONPath"
references to "Jinja2", adds on-blur validation, improves `tool_call_check` UX, and audits other
mode-style enums. Phase 1 already handled type picker reordering + "(recommended)" label.

## Steps

### Backend: `SetCheckProperties.mode` required (drop default)

1. In `libs/core/kiln_ai/datamodel/eval.py`, change `SetCheckProperties.mode` from
   `= "subset"` to no default (required field).

2. **Audit** other V2 `…Properties` for mode-style enum defaults that could silently mask user
   intent. Assessment:
   - `PatternMatchProperties.mode = "must_match"` — genuinely sensible default, keep.
   - `ContainsProperties.mode = "must_contain"` — genuinely sensible default, keep.
   - `ToolCallCheckProperties.match_mode = "all"` — genuinely sensible default, keep.
   - `ToolCallCheckProperties.on_unexpected_tools = "ignore"` — genuinely sensible default, keep.
   - `ArgMatch.match_mode = "exact"` — sensible default for argument matching, keep.
   - **Only `SetCheckProperties.mode`** has a problematic silent default ("subset" on backend vs
     "equal" on frontend → disagreement). Fix this one.

3. Fix existing tests that construct `SetCheckProperties` without an explicit `mode`.

4. Regenerate OpenAPI schema.

### Frontend: `set_check_form.svelte` — explicit mode

5. The form already defaults `mode: "equal"`. No change to the default value needed — it already
   sends an explicit mode. The backend change (making mode required) is the fix.

### Frontend: "JSONPath" → "Jinja2" wording across forms

6. In all forms with a `value_expression` field, change:
   - Label: keep "Value Expression"
   - Description: "Optional JSONPath or expression…" → "Optional Jinja2 expression to extract a
     value from the eval input before comparison. Leave blank to use the full model output."
   - Files: `exact_match_form.svelte`, `pattern_match_form.svelte`, `contains_form.svelte`,
     `set_check_form.svelte`

### Frontend: on-blur validation

7. **`pattern_match_form.svelte`** — add a `validate()` export and regex compilation check.
   Return error string if `new RegExp(pattern)` throws. Wire a blur handler on the pattern input
   to surface errors.

8. **`step_count_check_form.svelte`** — already has `validate()` for min/max bounds. Add blur
   handler to trigger inline error display.

9. **Literal-vs-reference XOR** — `exact_match_form.svelte`, `contains_form.svelte`,
   `set_check_form.svelte` — add `validate()` to enforce at least one source is populated.

### Frontend: `tool_call_check_form.svelte` improvements

10. Hide `on_unexpected_tools` when `match_mode` is "Never" (spec says it's ignored in that case).

11. Collapse `expected_args` by default per `70 §3.2` — use a toggle per tool-spec row.

### Type picker order + labels — Phase 1 already handled

12. Phase 1 reordered `ALL_V2_EVAL_TYPES` (llm_judge first) and set the label to
    "LLM as Judge (recommended)". The spec's intended order/labels from `70 §1`:
    - "LLM as Judge (recommended)" — done
    - "Code — Custom Python Code eval" — check if label matches
    - Remaining types — check labels match
    Only apply deltas if needed.

## Tests

### Python tests (backend)

- `test_set_check_mode_required`: `SetCheckProperties` without `mode` raises `ValidationError`.
- `test_set_check_mode_explicit_values`: each mode value ("subset", "superset", "equal") works
  when explicitly provided.
- Existing `test_set_check_xor_validator` updated to pass explicit `mode`.

### Frontend tests (vitest)

- `deterministic_forms.test.ts`: test `validate()` on `pattern_match` (valid/invalid regex),
  `step_count_check` (min>max, neither set), and XOR forms (neither source set).
- `tool_call_check_form` tests: verify `on_unexpected_tools` hidden when match_mode is "never";
  verify args section collapsed by default.
