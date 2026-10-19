# Cluster I Skeptic Verification: Deterministic-type & create-form UX

## 22-R71: set_check form default mode is "equal" but spec/Pydantic default is "subset"

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** CONTRADICTED
- **Corrected Severity:** moderate (behavior defect, not cosmetic)
- **Reasoning:** The Pydantic model (`eval.py:145`) defaults mode to `"subset"`. The spec (component 22 section 3.4, component 70 line 230) explicitly says Subset is the default. The form (`set_check_form.svelte:7`) initializes `mode: "equal"`. When a user creates a new set_check eval without touching the mode dropdown, `getProperties()` returns `mode: "equal"`, which is sent to the backend. The user silently gets strict equality instead of the intended subset semantics. This is a real functional defect: spec says subset, backend default says subset, but the create form overrides it to equal.
- **Evidence:**
  - `libs/core/kiln_ai/datamodel/eval.py:145` — `mode: Literal["subset", "superset", "equal"] = "subset"`
  - `app/web_ui/src/lib/components/eval_types/set_check_form.svelte:7` — `mode: "equal"`
  - Spec component 70 section 3.1: `"Subset (output values must all be in expected)" (default)`
  - Spec component 22 section 3.4: `mode: Literal["subset", "superset", "equal"] = "subset"`
  - `create_eval_config/+page.svelte:362` — `v2FormComponent.getProperties()` sends form value to backend
  - No intentional override found in RUN_NOTES.md or git history (introduced in commit `99f0c4332` Phase 6)

## 22-R67 / 70a-R38: exact_match comparison source uses select instead of radio group

- **Skeptic Verdict:** UPHELD_DOWNGRADE
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor (cosmetic)
- **Reasoning:** Spec section 3.1 explicitly says "radio group." Code uses a select dropdown (`exact_match_form.svelte:34`). Functionally equivalent for XOR selection. Inactive input hidden via `{#if}` rather than shown-but-disabled, which is actually cleaner UX (less visual noise). No functional impact. No intentional override documented.
- **Evidence:**
  - `app/web_ui/src/lib/components/eval_types/exact_match_form.svelte:34` — `inputType="select"`
  - Spec component 70 section 3.1: "Comparison source -- radio group"

## 22-R68 / 70a-R44: contains search string source uses select instead of radio group

- **Skeptic Verdict:** UPHELD_DOWNGRADE
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor (cosmetic)
- **Reasoning:** Same pattern as 22-R67. Select dropdown instead of radio. Functionally equivalent.
- **Evidence:**
  - `app/web_ui/src/lib/components/eval_types/contains_form.svelte:42` — `inputType="select"`

## 22-R69: set_check expected set source uses select instead of radio group

- **Skeptic Verdict:** UPHELD_DOWNGRADE
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor (cosmetic)
- **Reasoning:** Same pattern. Select dropdown instead of radio.
- **Evidence:**
  - `app/web_ui/src/lib/components/eval_types/set_check_form.svelte:50` — `inputType="select"`

## 22-R70 / 70a-R46: set_check expected_set uses textarea instead of tag-input

- **Skeptic Verdict:** UPHELD_DOWNGRADE
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor (cosmetic, different interaction model)
- **Reasoning:** Spec says "tag-input / multi-value field... Add items via enter or comma." Code uses a textarea with "One value per line" (`set_check_form.svelte:67-73`). The textarea approach does work for entering multiple values and is a reasonable alternative. The split/trim/filter logic at line 28-31 correctly converts newline-separated text to a clean list. Different interaction model but fully functional.
- **Evidence:**
  - `app/web_ui/src/lib/components/eval_types/set_check_form.svelte:67-73` — textarea with description "One value per line"
  - `set_check_form.svelte:28-31` — split/trim/filter conversion

## 22-R72: tool_call_check expected_args should be in collapsible section, collapsed by default

- **Skeptic Verdict:** REFUTED_IMPLEMENTED
- **Corrected Verdict:** MET (functionally equivalent)
- **Corrected Severity:** n/a
- **Reasoning:** For new evals, `arg_rows` initializes empty (from `properties.expected_tools.map(...)` which starts as `[]`). Inside each tool row, args render via `{#each arg_rows[item_index] ?? [] as arg_row}` which shows nothing when empty. User adds args via "+ Add Expected Argument" button. This achieves the spec goal: "keep the simple 'just check tool names' case clean" — args are absent by default, only appearing when explicitly added. No collapsible wrapper needed because there's nothing to collapse. The 70a-R52 reviewer already noted this as DEFERRED_OK for the same reason.
- **Evidence:**
  - `tool_call_check_form.svelte:10` — `expected_tools: []` (empty default)
  - `tool_call_check_form.svelte:23-31` — `arg_rows` computed from properties (empty for new eval)
  - `tool_call_check_form.svelte:125` — `{#each arg_rows[item_index] ?? []}` renders nothing when empty
  - `tool_call_check_form.svelte:167-172` — "+ Add Expected Argument" button is the entry point

## 22-R73 / 70a-R48: tool_call_check on_unexpected_tools should be hidden when match_mode="never"

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** MISSING
- **Corrected Severity:** minor (cosmetic/confusing but harmless at runtime)
- **Reasoning:** Spec section 3.1 explicitly says `on_unexpected_tools` is "Hidden when match mode is 'Never.'" The backend confirms this: `v2_eval_tool_call_check.py:79-84` returns early before the on_unexpected check when mode is "never", so the field has no effect. But the form (`tool_call_check_form.svelte:98-108`) always shows it. There is no conditional rendering based on `properties.match_mode`. This is a real UX gap: users see a control that does nothing when match_mode="never", which is confusing. However, since the backend ignores it, there is no functional impact on eval results.
- **Evidence:**
  - `tool_call_check_form.svelte:98-108` — no conditional on match_mode
  - Spec component 70 section 3.1: "Hidden when match mode is 'Never.'"
  - `v2_eval_tool_call_check.py:79-84` — returns early, ignoring on_unexpected_tools

## 22-R76: No on:blur client-side validation on any deterministic form

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor (polish)
- **Reasoning:** Spec section 3.2 says "All validation runs on blur (not on every keystroke) and again on Save attempt." No `on:blur` handlers found in any form component. `FormElement` itself has no blur handling. Server-side validation does run on save. Missing blur validation is real but minor — server catches invalid input.
- **Evidence:**
  - `grep -n blur form_element.svelte` — no results
  - No blur handlers in any eval type form component

## 22-R77: step_count_check validation present but not shown as inline error

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor (polish)
- **Reasoning:** `step_count_check_form.svelte:16-28` exports a `validate()` function that returns an error string, but the component itself has no inline error rendering. The error string is consumed externally (by the container at save time). No red inline error text below the min/max fields as spec requires.
- **Evidence:**
  - `step_count_check_form.svelte:16-28` — validate() returns string, no inline render

## 70a-R42: pattern_match regex validation on blur absent

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** MISSING
- **Corrected Severity:** minor (polish; server catches invalid regex at save)
- **Reasoning:** Spec requires `re.compile()` validation on blur for regex pattern. `pattern_match_form.svelte` has no blur handler, no regex validation. Server-side validation (`eval.py:114-122`) catches invalid regex at save time, so this is a missing UX polish, not a data integrity gap.
- **Evidence:**
  - `pattern_match_form.svelte:18-24` — plain input, no blur handler
  - `eval.py:114-122` — server-side re.compile() in model_validator

## 70a-R51: Value expression description says "JSONPath" but should say "Jinja2"

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** MISSING (incorrect help text)
- **Corrected Severity:** moderate (misleading documentation in the UI -- users will try JSONPath syntax and fail)
- **Reasoning:** The spec (component 70 section 3.2) says: "Value expression fields include a small '?' help icon linking to Jinja2 expression docs (or inline tooltip: 'Jinja2 expression evaluated against the eval input. Leave blank to use the full model output.')." The code says "Optional JSONPath or expression" in four places. The backend is definitively Jinja2: `v2_eval_helpers.py:10` imports `from kiln_ai.utils.jinja_engine import extract`, and `v2_eval_helpers.py:38` calls `extract(expression, data)`. The compile-time validation uses `compile_expression_or_raise` from the same Jinja2 engine. Calling this "JSONPath" will mislead users into trying JSONPath syntax (e.g., `$.response.answer`) which will fail at runtime. This is a correctness/documentation bug.
- **Evidence:**
  - `exact_match_form.svelte:70` — `"Optional JSONPath or expression to extract the value from the output before comparing."`
  - `pattern_match_form.svelte:41` — same "JSONPath" text
  - `contains_form.svelte:82` — same "JSONPath" text
  - `set_check_form.svelte:88` — same "JSONPath" text
  - `v2_eval_helpers.py:10` — `from kiln_ai.utils.jinja_engine import extract`
  - `v2_eval_helpers.py:38` — `result = extract(expression, data)`
  - Spec component 70 section 3.2: "Jinja2 expression evaluated against the eval input"
