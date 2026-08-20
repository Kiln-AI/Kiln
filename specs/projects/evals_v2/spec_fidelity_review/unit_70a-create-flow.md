# Spec-Fidelity Review: 70a-create-flow

**UNIT:** 70a-create-flow
**TITLE:** UI: create container, type picker, forms, test-run panel
**SPEC:** components/70_builder_and_onboarding.md (sections 1, 2, 3, 5)

Requirements: 52 total — MET 28, PARTIAL 9, MISSING 8, CONTRADICTED 3, DEFERRED_OK 3, CANNOT_VERIFY 1

---

## Requirements Table

### Section 1 — Create Container Architecture

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 70a-R01 | layout | CONTRADICTED | critical | Left pane = per-type authoring component, Right pane = "Test Run" | §1 Layout: "Standard Kiln left=main / right=details: Left — the injected per-type authoring component. Right — 'Test Run': pick a recent dataset item -> Run -> Results." | `+page.svelte`: No left/right split layout. The test pane is rendered as a `<Collapse>` element below the form (line 562), not as a side pane. Single-column layout. | Spec requires two-pane left/right layout; code uses single-column with test panel collapsed below form. |
| 70a-R02 | responsibility | CONTRADICTED | critical | Container loads test data = recent dataset items (generic, all types) | §1 table: "Load test data (recent dataset items)" owned by container | `+page.svelte`: No dataset items loaded. No API call to fetch recent dataset items. Instead, four free-text textareas are used (lines 568-621). | Spec requires container to load dataset items; code provides free-text inputs instead. |
| 70a-R03 | responsibility | MET | — | Container owns Run the test — uniform (config + input) -> scores call | §1 table: "Run the test — uniform (config + input) -> scores call" | `+page.svelte:run_test()` (line 209) calls `testV2Eval()` uniformly for all V2 types. Backend dispatches by type. | — |
| 70a-R04 | responsibility | MET | — | Container owns Save button + Save flow | §1 table: "Save button + Save flow" | `+page.svelte`: FormContainer with submit (line 510), `handle_submit()` (line 311), `do_save()` (line 336). | — |
| 70a-R05 | responsibility | MISSING | major | Container owns Clone / prefill-from-existing | §1 table: "Clone / prefill-from-existing" | No clone or prefill logic found in `+page.svelte`. No URL param to load an existing config's properties into the form. | Not implemented. |
| 70a-R06 | responsibility | MET | — | Container owns result-shape validation against output_scores | §1 table: "Result-shape validation against output_scores" | Server-side: `eval_api.py:996-998` runs the adapter which validates internally. Frontend relies on server validation (400 errors). | — |
| 70a-R07 | responsibility | MET | — | Per-type component renders the authoring form (left pane) | §1 table | `+page.svelte:547-558`: Uses `<svelte:component this={selected_metadata.createFormComponent}>` to render per-type forms. | — |
| 70a-R08 | responsibility | MET | — | Per-type component produces EvalConfig properties to hand up for save | §1 table | All form components export `getProperties()` (e.g. `exact_match_form.svelte:13`, `code_eval_form.svelte:31`). Container calls `v2FormComponent.getProperties()` at save time. | — |
| 70a-R09 | responsibility | MET | — | Per-type component declares requiresTrust: bool | §1 table | `registry.ts:63`: `V2EvalTypeMetadata` has `requiresTrust: boolean`; `code_eval` sets it true (line 148), others false. | — |
| 70a-R10 | interaction | MISSING | major | No edit-in-place; EvalConfigs are immutable. "Edit a config" = clone to new candidate. Saved configs render read-only. | §1: "No edit — clone only (E.17)... Saved configs render read-only; the container supports prefill-from-existing for the clone path." | No read-only view of saved configs found in this route. No clone functionality. | Clone-not-edit and read-only saved view not implemented in the create route. |
| 70a-R11 | interaction | MET | — | Type picker is initial state of container | §1: "Initial state of the container = Select Eval Type" | `+page.svelte:477-508`: When `!selected_v2_type`, renders the type picker grid. | — |
| 70a-R12 | interaction | PARTIAL | minor | "LLM as Judge (recommended)" listed first in the picker | §1: "'LLM as Judge (recommended)' first." | `registry.ts:39`: `ALL_V2_EVAL_TYPES` has `llm_judge` at position 7 (second-to-last), not first. The label is "LLM Judge" not "LLM as Judge (recommended)". | Wrong order (llm_judge is near last, not first) and missing "(recommended)" suffix. |
| 70a-R13 | interaction | PARTIAL | minor | Type order: then "Code — Custom Python Code eval", "Exact Match", "Pattern Match (regex)", "Contains", "Set Check", "Tool Call Check", "Step Count Check" | §1 type picker list | `registry.ts:39-48`: Order is exact_match, pattern_match, contains, set_check, tool_call_check, step_count_check, llm_judge, code_eval. Also labels differ: "Code Eval" not "Code — Custom Python Code eval", "Pattern Match" not "Pattern Match (regex)". | Order and labels diverge from spec. |
| 70a-R14 | interaction | PARTIAL | minor | No applicability filtering — all V2 types always listed | §1: "No applicability filtering — all V2 types always listed." | `+page.svelte:486`: Iterates `ALL_V2_EVAL_TYPES` with no filtering. MET for the requirement itself. But the picker also includes deterministic types even if trace-related — this is correct per spec. | Functionally met, though ordering deviates (see R12/R13). |
| 70a-R15 | interaction | PARTIAL | minor | On select: push history / update URL the SvelteKit-official way, so Back returns to the picker | §1: "On select: push history / update URL the SvelteKit-official way, so Back returns to the picker." | `+page.svelte:158-159`: `select_v2_type` just sets a local variable. No `goto()`, no `pushState()`, no URL update. Back button is a manual `go_back_to_type_picker()` (line 162). URL doesn't change. | No URL/history push on type selection. Browser Back won't return to picker — only the manual "Back" button works. |
| 70a-R16 | interaction | MET | — | Back returns to picker | §1 | `+page.svelte:519-525`: "Back" button calls `go_back_to_type_picker()` which resets `selected_v2_type = null`, returning to picker view. | — |
| 70a-R17 | interaction | MET | — | system_prompt NOT exposed in LLM-judge create form | §1: "The system_prompt field is not exposed in the LLM-judge create form." | `llm_judge_form.svelte`: No `system_prompt` field anywhere in the form. Confirmed via grep. | — |

### Section 2 — Code-Eval Create UI

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 70a-R18 | editor | MET | — | CodeMirror 6 with @codemirror/lang-python | §2 Editor: "CodeMirror 6 with @codemirror/lang-python" | `code_editor.svelte:25`: `import("@codemirror/lang-python")` dynamically imported. | — |
| 70a-R19 | editor | MET | — | Lazy-loaded (imported only on code-eval page) | §2: "Lazy-loaded — imported only on the code-eval page so CM6 stays out of the default/bundled load" | `code_editor.svelte:16-28`: All CM6 modules imported via dynamic `import()` inside `onMount`. | — |
| 70a-R20 | editor | MET | — | Loads with a minimal valid eval example | §2: "Loads with a minimal valid eval example." | `code_eval_form.svelte:15`: `code: generate_default_code(output_scores)` — produces a minimal score function. | — |
| 70a-R21 | editor | MET | — | Built as a reusable component | §2: "Built as a reusable component" | `code_editor.svelte` is a standalone reusable component in `$lib/components/`. | — |
| 70a-R22 | editor | DEFERRED_OK | — | Format/lint buttons are cut | §2: "Format / lint buttons are cut" | No format/lint buttons present. | Correctly omitted. |
| 70a-R23 | editor | MET | — | "See examples" -> tabbed modal with common cases + "Use this template" button | §2: "'See examples' -> tabbed modal of a few common cases... each with a 'Use this template' button." | `code_eval_form.svelte:82-87`: "See examples" button opens `examples_dialog`. Lines 118-152: Tabbed modal with examples. Line 130: "Use This Example" button. | — |
| 70a-R24 | editor | PARTIAL | minor | "Python" label top-left of the CodeMirror box | §2 Editor: "'Python' label top-left of the box." | `code_eval_form.svelte`: No explicit "Python" label on the editor. There's a "Score Function" label (line 79) and a "Write a Python function..." description (line 72), but no "Python" label on the editor box itself. `code_editor.svelte` has no label. | Missing explicit "Python" label positioned top-left of the editor box. |
| 70a-R25 | test-pane | CONTRADICTED | critical | Test pane Input Section lists recent dataset items to pick from. Manual free-text input is cut. | §2: "'Test Run' -> Input Section lists recent dataset items to pick from. Manual free-text input is cut." | `+page.svelte:567-621`: Test panel uses four free-text textareas (final_message, task_input, trace, reference_data). No dataset item picker. No dataset items loaded. | Spec explicitly requires dataset-item picker and forbids free-text. Code does the exact opposite. |
| 70a-R26 | test-pane | MISSING | minor | Reference data via an Advanced expander | §2: "Reference data is available via an Advanced expander" | `+page.svelte:613-621`: reference_data textarea shown inline alongside other fields — no "Advanced" expander wrapping it. | Reference data not behind an Advanced expander. |
| 70a-R27 | test-pane | MISSING | minor | Trace comes from the selected dataset item | §2: "the trace comes from the selected dataset item." | No dataset item selection; trace is a manual JSON textarea input. | Trace is free-text, not auto-populated from dataset item. |
| 70a-R28 | test-pane | MET | — | Async UX: spinner + Cancel while running | §2: "Async UX: spinner + Cancel while running" | `+page.svelte:636-653`: Spinner shown during test_loading, Cancel button calls `cancel_test()` which aborts via AbortController. | — |
| 70a-R29 | test-pane | MISSING | major | Empty-dataset state: "Run your task to generate sample inputs." and Save-Without-Testing becomes the only path | §2: "Empty-dataset state: 'Run your task to generate sample inputs.' ... Save Without Testing is the only path" | No dataset loading, so no empty-dataset detection. No such message displayed anywhere. | Not implemented — no dataset awareness. |
| 70a-R30 | test-pane | PARTIAL | minor | Return-shape check vs output_scores gates Save | §2: "A successful test run (executed and returned a valid shape matching output_scores) enables Save." | `+page.svelte:328`: Save-without-testing gate checks `!test_has_run` — but `test_has_run` is set true as soon as any test completes (line 277), regardless of whether scores match output_scores shape. No frontend shape validation. Server may reject at save time but test-run doesn't gate save based on shape. | test_has_run doesn't distinguish shape-valid from shape-invalid results. |
| 70a-R31 | save | MET | — | "Save Without Testing" confirm modal exists | §2: "'Save Without Testing' confirm modal" | `+page.svelte:725-747`: Dialog titled "Save Without Testing?" with "Cancel" and "Save Anyway" buttons. | — |
| 70a-R32 | save | PARTIAL | minor | Save-Without-Testing modal copy: "I know, you're a great coder, but it never hurts to run it once." Red Save Without Testing / Cancel buttons | §2: "I know, you're a great coder, but it never hurts to run it once." Buttons: red Save Without Testing / Cancel." | `+page.svelte:743-746`: Copy is "You haven't tested this judge yet. Running a quick test helps catch issues before saving. Are you sure you want to save without testing?" Button label is "Save Anyway" (with `isError: true` for red), not "Save Without Testing". | Copy differs from spec. Button label is "Save Anyway" not "Save Without Testing". |
| 70a-R33 | trust | MET | — | Trust gate modal on first run or save for code_eval | §2: "'Trust this code?' modal on first run or save" | `+page.svelte:267-275`: On run, if skipped_reason is `code_eval_not_trusted`, shows trust_dialog. Line 313-320: On save, checks trust and shows dialog. | — |
| 70a-R34 | trust | PARTIAL | minor | Trust modal copy: "never paste code from a stranger or the internet here." | §2: "never paste code from a stranger or the internet here." | `+page.svelte:716-720`: Copy is "This eval runs Python code on your machine. Only proceed if you trust eval code inside this project." | Copy differs from spec wording, though intent is similar. |
| 70a-R35 | trust | MET | — | Trust answer held in-memory, window-scoped; re-asked on next app launch; no disk/DB persistence | §2: "in-memory, window-scoped; re-asked on next app launch; no disk/DB persistence." | `v2_eval_code_eval.py:22`: `_trusted_projects: set[str] = set()` — module-level set, in-memory only. Resets on process restart. | — |
| 70a-R36 | badge | MET | — | Beta label under the header — code-eval only. Deterministic types ship stable. | §2: "Beta label under the header — code-eval only." | `code_eval_form.svelte:68-70`: `<span class="badge badge-sm badge-primary badge-outline font-medium">Beta</span>`. No beta badge on deterministic forms. | — |
| 70a-R37 | interaction | DEFERRED_OK | — | P2: "Ask assistant for help" button (not V2.0-gating) | §2: "P2 (not V2.0-gating): 'Ask assistant for help' button" | Not present — correctly deferred as P2. | — |

### Section 3 — Deterministic-Type Create Components

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 70a-R38 | form-layout | PARTIAL | minor | exact_match: "Comparison source — radio group" with literal vs reference key. Radio disables inactive input. | §3.1: "Comparison source — radio group: 'Compare against a literal value' / 'Compare against reference data key.' ... Radio groups for XOR fields (literal vs reference) disable the inactive input." (§3.2) | `exact_match_form.svelte:34-37`: Uses a `select` dropdown ("Fixed Expected Value" / "Reference Data Key"), not a radio group. The inactive field is hidden (`{#if}`) rather than shown-but-disabled. | Uses select dropdown instead of radio group. Inactive input hidden not disabled. |
| 70a-R39 | form-layout | MET | — | exact_match: Value expression — optional text input | §3.1 | `exact_match_form.svelte:67-74`: Optional input field for value_expression. | — |
| 70a-R40 | form-layout | MET | — | exact_match: Case sensitive — checkbox (default checked) | §3.1 | `exact_match_form.svelte:5,76-81`: `case_sensitive: true` default, checkbox control. | — |
| 70a-R41 | form-layout | MET | — | pattern_match: Regex pattern — text input (required) | §3.1 | `pattern_match_form.svelte:18-24`: Input for pattern. | — |
| 70a-R42 | form-layout | MISSING | minor | pattern_match: Regex validation on blur (re.compile()). Show error if invalid. | §3.1: "Validation: re.compile() on blur; show error if invalid regex." | `pattern_match_form.svelte`: No blur validation, no regex validation logic. | No client-side regex validation. |
| 70a-R43 | form-layout | MET | — | pattern_match: Mode — select: "Must match" (default) / "Must not match." | §3.1 | `pattern_match_form.svelte:26-33`: Select with must_match (default) and must_not_match. | — |
| 70a-R44 | form-layout | PARTIAL | minor | contains: Radio group for literal vs reference source. Disable inactive. | §3.1/§3.2 | `contains_form.svelte:29-57`: Uses select dropdown, not radio. Inactive field hidden not disabled. | Same issue as exact_match. |
| 70a-R45 | form-layout | MET | — | set_check: Mode with Subset/Superset/Equal | §3.1 | `set_check_form.svelte:35-44`: Select with equal, subset, superset options. | — |
| 70a-R46 | form-layout | MISSING | minor | set_check: Tag-input / multi-value field (add items via enter or comma) | §3.1: "tag-input / multi-value field for expected_set (list of strings). Add items via enter or comma." | `set_check_form.svelte:67-72`: Uses a plain textarea with "One value per line" — not a tag input with enter/comma add. | Textarea instead of tag-input widget. |
| 70a-R47 | form-layout | MET | — | tool_call_check: Dynamic list builder with add/remove tool rows | §3.1 | `tool_call_check_form.svelte:110-174`: Uses `FormList` component for dynamic tool rows with add/remove. | — |
| 70a-R48 | form-layout | MISSING | minor | tool_call_check: "On unexpected tools" hidden when match mode is "Never" | §3.1: "On unexpected tools — ... Hidden when match mode is 'Never.'" | `tool_call_check_form.svelte:98-108`: `on_unexpected_tools` field always visible regardless of `match_mode` value. No conditional rendering. | Field always shown. |
| 70a-R49 | form-layout | MET | — | step_count_check: Count type select with tool_calls / model_responses / turns | §3.1 | `step_count_check_form.svelte:32-41`: Select with all three options. | — |
| 70a-R50 | form-layout | MET | — | step_count_check: Validation — at least one min/max must be set; min <= max | §3.1 | `step_count_check_form.svelte:16-27`: `validate()` function checks both conditions. | — |
| 70a-R51 | form-convention | MISSING | minor | Value expression fields include "?" help icon or tooltip about Jinja2 expressions | §3.2: "Value expression fields include a small '?' help icon linking to Jinja2 expression docs (or inline tooltip)." | `exact_match_form.svelte:70`: Description says "Optional JSONPath or expression" — no "?" icon, no Jinja2 mention, no tooltip link. Same for other forms. | No help icon/tooltip, description mentions "JSONPath" not "Jinja2". |
| 70a-R52 | form-convention | DEFERRED_OK | — | tool_call_check: arg-matching section collapsed by default | §3.2: "The arg-matching section is collapsed by default to keep the simple 'just check tool names' case clean." | `tool_call_check_form.svelte:125`: Arg rows start empty (`arg_rows` initialized from properties which default to empty expected_args). User adds via button. Effectively collapsed/absent by default. | Functional equivalent achieved. |

---

## Verifier-Added Requirements (source: verifier_added)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 70a-R53 | interaction | CANNOT_VERIFY | — | Container's test-run is not per-component (all types get test-run for free) | §1: "test-run is not per-component. Because the backend already dispatches by type, the container runs every type's test the same way" | For non-LLM-judge V2 types, test-run panel shows. For LLM-judge, the test panel does not appear (line 560: `{#if can_submit_v2}` which excludes llm_judge). LLM judge presumably has its own test mechanism or this is intentional. | Cannot fully verify intent for LLM judge exclusion. |

---

## Summary of Non-MET/Non-DEFERRED_OK Findings

**CONTRADICTED (3):**
1. **70a-R01** [critical] — Layout: spec requires left/right two-pane; code is single-column.
2. **70a-R02** [critical] — Container must load dataset items; code provides no dataset loading.
3. **70a-R25** [critical] — Test pane must use dataset-item picker with free-text cut; code uses free-text textareas.

**MISSING (8):**
4. **70a-R05** [major] — Clone / prefill-from-existing not implemented.
5. **70a-R10** [major] — Saved configs read-only view not in this route.
6. **70a-R29** [major] — Empty-dataset state not implemented.
7. **70a-R26** [minor] — Reference data not behind Advanced expander.
8. **70a-R27** [minor] — Trace not auto-populated from dataset item.
9. **70a-R42** [minor] — No regex blur validation in pattern_match form.
10. **70a-R46** [minor] — No tag-input widget for set_check expected_set.
11. **70a-R48** [minor] — on_unexpected_tools not hidden when match_mode is "Never".
12. **70a-R51** [minor] — No Jinja2 help icon/tooltip on value expression fields.

**PARTIAL (9):**
13. **70a-R12** [minor] — LLM judge not first in picker, missing "(recommended)".
14. **70a-R13** [minor] — Type order/labels diverge from spec.
15. **70a-R15** [minor] — No URL/history push on type select.
16. **70a-R24** [minor] — No "Python" label on CodeMirror box.
17. **70a-R30** [minor] — Return-shape check doesn't gate save (test_has_run ignores shape validity).
18. **70a-R32** [minor] — Save-Without-Testing modal copy/button label differ.
19. **70a-R34** [minor] — Trust modal copy differs from spec.
20. **70a-R38** [minor] — XOR fields use select dropdown not radio group, inactive hidden not disabled.
21. **70a-R44** [minor] — Same as R38 for contains form.
