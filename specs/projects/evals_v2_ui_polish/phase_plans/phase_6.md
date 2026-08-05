---
status: complete
---

# Phase 6 — Code Judge form + LLM cards

## Overview

Two visual-only changes to polish the Code Judge and LLM Judge create forms:

1. **Code Judge form (`code_eval_form.svelte`):** Replace the ad-hoc "Score Function" label + "See examples" button with the standard `FormElement` `header_only` + `inline_action` pattern (adding subtitle, tooltip, and renaming trigger to "More Examples"). Remove the footer paragraph (the function-signature hint). Consolidate the redundant top badge+one-liner that duplicates the intro section added in Phase 3.

2. **LLM Judge form (`llm_judge_form.svelte`):** Shrink model cards ~40% (`w-[200px]` -> `w-[120px]`, icon `w-10 h-10` -> `w-6 h-6`) and algorithm cards ~40% (`w-[260px]` -> `w-[156px]`), with tighter padding/gaps to fit within the narrower left column alongside the test-run pane.

## Steps

1. **`code_eval_form.svelte` — Replace Score Function header**
   - Remove the ad-hoc `<div class="flex flex-col gap-1">` / `<label>` / `<button>` block for "Score Function" + "See examples".
   - Replace with a `FormElement` using `inputType="header_only"`, `label="Score Function"`, `description="Define a Python score function to evaluate the model's work."`, `info_description` tooltip text, and `inline_action` pointing to `show_examples` with label "More Examples".
   - Place the `CodeEditor` immediately after (as sibling, not inside FormElement slot).

2. **`code_eval_form.svelte` — Remove footer paragraph**
   - Delete the `<div class="text-xs text-gray-400 mt-1">` block containing the function signature hint (lines 96-103). The subtitle + examples cover this information.

3. **`code_eval_form.svelte` — Consolidate redundant top badge/line**
   - Remove the `<div class="flex items-center gap-2">` block with the Beta badge and one-liner description (lines 66-74). This is superseded by the `eval_type_intro` added in Phase 3.

4. **`llm_judge_form.svelte` — Shrink model cards**
   - Change card width from `w-[200px]` to `w-[120px]`.
   - Remove `aspect-[5/6]`.
   - Shrink icon from `w-10 h-10` to `w-6 h-6`.
   - Reduce card padding from `p-4` to `p-3`.
   - Reduce inner gap from `gap-3` to `gap-2`.

5. **`llm_judge_form.svelte` — Shrink algorithm cards**
   - Change card width from `w-[260px]` to `w-[156px]`.
   - Remove `aspect-[5/6]`.
   - Reduce padding from `p-6` to `p-4`.
   - Shrink radio margin from `my-8` to `my-4`.

6. **`form_element_stub.svelte` — Add `inline_action` prop**
   - Add the `inline_action` prop to the stub so tests can verify the action renders.
   - Render `inline_action.label` in a testable data attribute.

7. **`code_eval_form.test.ts` — Update tests**
   - Update "Beta badge" test: assert the standalone badge is gone (no `.badge` in the form).
   - Update "See examples" test: assert "More Examples" label via the form element stub's inline_action data attribute.
   - Remove/update the "score function signature hint" test (footer paragraph removed).
   - Remove/update the "per-type ranges" test (footer paragraph removed).
   - Add test: FormElement with `header_only` + label "Score Function" is present.
   - Add test: FormElement has description/subtitle text.
   - Add test: FormElement has info_description (tooltip text).

8. **`llm_judge_form.svelte` — Add test file for card sizing assertions**
   - Since there is no existing LLM judge form test file, verify sizing via the component tests for code_eval_form (the LLM form changes are purely CSS class changes; structural tests added in code_eval_form cover the pattern).

## Tests

- Code judge form renders `FormElement` with `inputType="header_only"` and `label="Score Function"`.
- Code judge form `FormElement` has `inline_action` with label "More Examples".
- Code judge form `FormElement` has subtitle (description) text.
- Code judge form `FormElement` has tooltip (info_description) text.
- Code judge form does NOT contain the standalone Beta badge.
- Code judge form does NOT contain the footer paragraph text ("score(output, trace, reference_data, task_input)").
- Code judge form still renders the examples dialog.
- Code judge form `getProperties()` still works correctly.
- LLM form model cards use `w-[120px]` (structural/class verification in template).
- LLM form algorithm cards use `w-[156px]` (structural/class verification in template).
