---
status: complete
---

# Phase 5: Form Polish (Radio Groups + Tag Input)

## Overview

Additive UI polish for deterministic eval config forms. Two changes:

1. Replace the `<select>` dropdown for the literal-vs-reference XOR choice with radio groups that disable the inactive option's inputs, making the mutual exclusivity visually obvious (exact_match, contains, set_check).
2. Replace set_check's textarea-based `expected_set` entry with a tag-style input (type + Enter/comma to add, click X to remove).

These are cleanly additive — no changes to validate() exports, getProperties() contracts, save/test gating, blur validation, or any Phase 4 structural fixes.

## Steps

1. **Create a `TagInput` component** (`app/web_ui/src/lib/components/eval_types/tag_input.svelte`). The existing `tag_picker.svelte` is tightly coupled to project/task tag APIs (TagDropdown, server-side tag lookups) and is not reusable for a simple string-list entry. Build a lightweight tag input:
   - Props: `tags: string[]`, `placeholder: string`, `disabled: boolean`, `id: string`
   - UI: renders tags as DaisyUI badges with X remove buttons; an inline text input; Enter/comma adds the trimmed input as a new tag (deduped); Backspace on empty input removes the last tag.
   - Two-way binding on `tags`.

2. **Convert `exact_match_form.svelte`** — replace the `<select>` "Match Source" with a radio group:
   - Two radio options: "Fixed Expected Value" / "Reference Data Key"
   - The selected option's input is enabled; the other is hidden (matching current `{#if}` pattern — keep hiding, not disabling, since the current pattern already does conditional rendering and the spec says "disable inactive" which we implement by only showing the active one's input, consistent with Phase 4 blur validation already working on the visible input).
   - Preserve `source` variable, `validate()`, `getProperties()` unchanged.

3. **Convert `contains_form.svelte`** — same radio-group treatment for the "Search String Source" XOR:
   - Radio: "Fixed Substring" / "Reference Data Key"
   - Same show/hide pattern for the child inputs.

4. **Convert `set_check_form.svelte`** — radio group for "Expected Set Source" XOR + tag-input:
   - Radio: "Fixed Expected Set" / "Reference Data Key"
   - Replace the textarea `expected_set_text` with the new `TagInput` component bound to `properties.expected_set`.
   - Remove the `expected_set_text` intermediary and `$:` reactive text-splitting logic.

5. **Update `form_element_stub.svelte`** if needed for test compatibility (should not be needed since we use native radio inputs, not FormElement for the radios).

6. **Write tests** for the new TagInput component and update deterministic form tests.

## Tests

- **TagInput component test** (`tag_input.test.ts`): verifies initial render of tags, adding via Enter, dedup, removal via X button.
- **ExactMatchForm radio group**: verify that the `source` state drives which input renders; validate() still works correctly for both sources.
- **ContainsForm radio group**: same as ExactMatchForm pattern.
- **SetCheckForm radio + tag-input**: verify tag-input renders for expected_set source; validate() still catches empty set; getProperties() returns the array.
- All existing deterministic_forms.test.ts tests continue to pass (no regressions).
