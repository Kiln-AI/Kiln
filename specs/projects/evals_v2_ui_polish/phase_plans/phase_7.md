---
status: complete
---

# Phase 7 — Deterministic forms I (shared form_parts + value-expression family)

## Overview

Create three shared `form_parts` components and redesign the three "value-expression family"
deterministic forms (`exact_match`, `pattern_match`, `contains`) using them. The redesign replaces
nested radio-with-input patterns with progressive disclosure (radio group above, then only the
relevant input shown), adds section titles, relabels `value_expression` to "Output Value to
Compare" with a Jinja tooltip, and uses the shared components for consistency.

**Critical constraint:** Each form's `getProperties()` and `validate()` contracts are preserved
exactly -- same property shapes, same validation outcomes, same on-blur behavior (pattern_match
regex check). The builder calls these the same way before and after.

## Steps

1. **Create `form_parts/form_section.svelte`**
   - A titled section wrapper: bold section title + optional subtitle + slot for content.
   - Props: `title`, `subtitle?`, `testid?`.
   - Renders a `div` with heading + description + `<slot />`.

2. **Create `form_parts/disclosure_radio_group.svelte`**
   - A Kiln-styled radio group that drives progressive disclosure.
   - Props: `name` (radio group name), `options` (array of `{value, label, description}`),
     `bind:selected` (two-way binding for the selected value).
   - Renders radio buttons with label + description for each option.
   - Does NOT render follow-up inputs inline (the parent conditionally shows the right input
     based on the selected value). This replaces the nested-radio pattern.

3. **Create `form_parts/output_value_field.svelte`**
   - The shared `value_expression` control wrapped in a `form_section`.
   - Props: `bind:value` (binds to `properties.value_expression`), `id_prefix` (for unique IDs).
   - Label: "Output Value to Compare".
   - Subtitle: "Leave blank to compare the entire model output, or use a Jinja expression to
     extract fields from JSON output."
   - Tooltip (info_description): explains what Jinja is -- a templating syntax for pulling values
     out of structured output, e.g. `{{ user.email }}`.
   - Uses `FormElement` with `inputType="input"`, `optional=true`.

4. **Redesign `exact_match_form.svelte`**
   - Section "Expected Value": `disclosure_radio_group` with options "Fixed value" / "Value from
     reference data", then conditionally show either the expected_value input or reference_key
     input (only the active branch visible).
   - Section "Output Value to Compare": `output_value_field` + `case_sensitive` checkbox.
   - **Preserve:** `getProperties()` returns the same `ExactMatchProperties` shape. `validate()`
     returns the same errors for the same conditions. Radio source switching still clears the
     inactive field (expected_value or reference_key set to null).

5. **Redesign `pattern_match_form.svelte`**
   - Section "Pattern": regex input with on-blur validation (preserved exactly), tooltip
     explaining what a regular expression is.
   - Section "Match Mode": `disclosure_radio_group` with "Must match" / "Must not match"
     (replaces the select dropdown -- both are valid, but radio is clearer for 2 options).
   - Section "Output Value to Compare": `output_value_field`.
   - **Preserve:** `getProperties()` returns the same `PatternMatchProperties`. `validate()`
     returns the same errors. On-blur regex check + reactive validation unchanged.

6. **Redesign `contains_form.svelte`**
   - Section "Expected Substring": `disclosure_radio_group` with "Fixed substring" / "Value from
     reference data", then conditionally show substring or reference_key input.
   - Section "Match Mode": `disclosure_radio_group` with "Must contain" / "Must not contain".
   - Section "Output Value to Compare": `output_value_field` + `case_sensitive` checkbox.
   - **Preserve:** `getProperties()` returns the same `ContainsProperties`. `validate()` returns
     the same errors. Radio source switching still clears the inactive field.

7. **Add tests for shared form_parts**
   - `form_section` renders title, subtitle, and slot content.
   - `disclosure_radio_group` renders options, selects default, fires change.
   - `output_value_field` renders with correct label, description, tooltip.

8. **Extend deterministic_forms.test.ts with regression tests**
   - Each redesigned form still emits the SAME `getProperties()` output for representative inputs.
   - Each form's `validate()` still passes/fails the same cases.
   - Progressive disclosure: radio group renders, switching source clears inactive value.
   - Relabel: "Output Value to Compare" label present in each form.
   - Jinja tooltip text present in each form (via info_description).
   - Pattern match on-blur regex error still works.

## Data contract preservation

### exact_match_form
- `getProperties()` -> `{ type: "exact_match", case_sensitive, value_expression, expected_value, reference_key }`
- `validate()`: "Expected value is required." when source=expected_value and empty; "Reference key is required." when source=reference_key and empty; null otherwise.
- On source switch: sets the inactive field to null.

### pattern_match_form
- `getProperties()` -> `{ type: "pattern_match", pattern, mode, value_expression }`
- `validate()`: "Regular expression is required." when pattern empty; "Invalid regular expression pattern." when regex invalid; null otherwise.
- On-blur: `validate_regex()` sets `regex_error` inline.

### contains_form
- `getProperties()` -> `{ type: "contains", case_sensitive, mode, value_expression, substring, reference_key }`
- `validate()`: "Substring is required." when source=substring and empty; "Reference key is required." when source=reference_key and empty; null otherwise.
- On source switch: sets the inactive field to null.

## Tests

- `form_section` renders title and subtitle text.
- `form_section` renders slot content.
- `disclosure_radio_group` renders all option labels.
- `disclosure_radio_group` selects default option.
- `disclosure_radio_group` updates selected value on click.
- `output_value_field` renders "Output Value to Compare" label.
- `output_value_field` renders Jinja tooltip text.
- ExactMatch: `getProperties()` returns correct shape with expected_value set.
- ExactMatch: `getProperties()` returns correct shape with reference_key set.
- ExactMatch: `validate()` errors preserved (expected_value required, reference_key required).
- ExactMatch: switching source clears inactive value (both directions).
- ExactMatch: "Output Value to Compare" label present.
- PatternMatch: `getProperties()` returns correct shape.
- PatternMatch: `validate()` errors preserved (empty, invalid regex).
- PatternMatch: on-blur regex error still works.
- PatternMatch: "Output Value to Compare" label present.
- Contains: `getProperties()` returns correct shape with substring set.
- Contains: `getProperties()` returns correct shape with reference_key set.
- Contains: `validate()` errors preserved (substring required, reference_key required).
- Contains: switching source clears inactive value (both directions).
- Contains: "Output Value to Compare" label present.
- Contains: Jinja tooltip text present.
