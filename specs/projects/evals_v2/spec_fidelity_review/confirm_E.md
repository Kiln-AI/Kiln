# Cluster E — Create-flow structural divergences: Skeptic Verification

## 70a-R01: Layout (two-pane vs single-column)

- **Skeptic Verdict:** UPHELD_DOWNGRADE
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor
- **Reasoning:** The spec (§1 Layout) says "Standard Kiln left=main / right=details: Left — the injected per-type authoring component. Right — 'Test Run'." The phase 6 plan (line 91) reinterprets this as "a collapsible section below the form" and explicitly mentions "Only shown for V2 types." The implementation uses a Collapse below the form (line 562). While this deviates from the spec's two-pane language, the phase 6 plan made this a deliberate design decision for the implementation — using a collapsible below-form layout instead of a side panel. This is a minor layout divergence, not a critical structural failure, since the test-run functionality IS accessible. Downgraded from critical because the phase plan explicitly chose this approach and the core functionality (test before save) is present.
- **Evidence:** Spec: `70_builder_and_onboarding.md:47-49`. Phase 6 plan: `phase_plans/phase_6.md:91` ("a collapsible section below the form"). Code: `+page.svelte:562` (`<Collapse title="Test Your Judge">`).

---

## 70a-R02: Container loads dataset items

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** CONTRADICTED
- **Corrected Severity:** major
- **Reasoning:** The spec (§1 responsibility table) assigns "Load test data (recent dataset items)" to the container. The code loads no dataset items and makes no API call to fetch them. The phase 6 plan (line 91) relaxes this to "paste/pick a sample input" but even the "pick" aspect was not implemented — only free-text paste exists. This is a real gap: dataset item loading is absent.
- **Evidence:** Spec: `70_builder_and_onboarding.md:57` ("Load test data (recent dataset items)"). Code: `+page.svelte` — no API call for dataset items, only manual text inputs (lines 567-621). Phase 6 plan: `phase_6.md:91` says "paste/pick" but pick was never built.

---

## 70a-R25: Test pane must use dataset-item picker; free-text cut

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** CONTRADICTED
- **Corrected Severity:** major (calibration case — independently confirmed)
- **Reasoning:** This is the stated calibration case. The spec is explicit in two places: §1 ("pick a recent dataset item") and §2 ("Input Section lists recent dataset items to pick from. Manual free-text input is cut."). The code uses four free-text textareas (lines 567-621) with no dataset-item picker. The phase 6 plan partially relaxes this to "paste/pick a sample input" (line 91) but even the "pick" option was not implemented. The code directly contradicts the spec's explicit "Manual free-text input is cut" directive. Downgrading from critical to major because (a) the test-run functionality still works with manual input and (b) the phase plan shows the implementer intended to allow paste, but the picker half was dropped. This is the highest-priority UX gap in this cluster.
- **Evidence:** Spec: `70_builder_and_onboarding.md:100` ("Manual free-text input is cut"). Code: `+page.svelte:567-621` (four textareas). Phase plan: `phase_6.md:91` ("paste/pick").

---

## 70a-R26: Reference data via Advanced expander

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** MISSING
- **Corrected Severity:** trivial
- **Reasoning:** The spec §2 says "Reference data is available via an Advanced expander." The code shows `reference_data` as an inline textarea alongside other fields (line 613). However, given that the test panel itself uses free-text (contradicting the spec's picker-based design), this finding is downstream of 70a-R25 — if a picker were implemented, reference data would come from the selected item. In the current free-text design, having reference_data visible is reasonable. Trivial severity.
- **Evidence:** Spec: `70_builder_and_onboarding.md:100`. Code: `+page.svelte:613-621`.

---

## 70a-R27: Trace from selected dataset item

- **Skeptic Verdict:** UPHELD_DOWNGRADE
- **Corrected Verdict:** MISSING
- **Corrected Severity:** trivial
- **Reasoning:** Same as R26 — downstream of 70a-R25. If a dataset-item picker existed, trace would auto-populate from the selected item. In the current free-text design, manual trace entry is the logical fallback. This is a consequence of the missing picker, not a separate bug.
- **Evidence:** Spec: `70_builder_and_onboarding.md:100`. Code: `+page.svelte:598-610` (manual JSON textarea).

---

## 70a-R29: Empty-dataset state

- **Skeptic Verdict:** UPHELD_DOWNGRADE
- **Corrected Verdict:** MISSING
- **Corrected Severity:** minor (was major)
- **Reasoning:** The spec §2 says "Empty-dataset state: 'Run your task to generate sample inputs.' ... Save Without Testing is the only path." This is entirely absent — no dataset awareness exists, so there's no detection of empty-dataset state. However, because the implementation uses free-text input (not a picker), an empty-dataset state is moot — the user can always type test input. The empty-dataset state was designed for the picker UX where having no items to pick from would be a dead end. In the current free-text design, this is not a functional blocker. Downgrading from major to minor since the concern the spec was solving (dead-end UX when no data) doesn't manifest with the current free-text approach.
- **Evidence:** Spec: `70_builder_and_onboarding.md:103`. Code: `+page.svelte` — no dataset loading, no empty state messaging.

---

## 70a-R30: Return-shape check gates Save

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor
- **Reasoning:** The spec §2 says "A successful test run (executed and returned a valid shape matching output_scores) enables Save." The code sets `test_has_run = true` (line 277) as soon as any test completes, regardless of shape validity. However, the backend DOES validate the return shape — if the scores don't match output_scores, the server returns errors (visible in the test result UI). The gap is that Save is enabled even after a shape-invalid test result. This is minor because (a) the server still rejects invalid configs at save time and (b) the user sees the error in the test panel.
- **Evidence:** Spec: `70_builder_and_onboarding.md:107`. Code: `+page.svelte:277` (`test_has_run = true` unconditionally on test completion).

---

## 70a-R05: Clone / prefill-from-existing

- **Skeptic Verdict:** REFUTED_DEFERRED
- **Corrected Verdict:** DEFERRED_OK
- **Corrected Severity:** n/a (not a defect)
- **Reasoning:** The phase 6 plan explicitly states (line 23): "Editing V2 eval configs in place. EvalConfigs are immutable: the user workflow is clone-and-modify (not in scope for this phase)." And line 558: "Edit/clone flow for eval configs (future phase)." And line 127-129: "If the user wants to iterate, they create a new config (potentially pre-filling from an existing one in a future phase)." This was a deliberate scope cut for phase 6. The spec describes it as part of the container's responsibilities, but the implementation plan explicitly defers it.
- **Evidence:** Phase 6 plan: `phase_6.md:23` ("not in scope for this phase"), `phase_6.md:558` ("Edit/clone flow for eval configs (future phase)").

---

## 70a-R10: Saved configs render read-only / clone-not-edit

- **Skeptic Verdict:** REFUTED_DEFERRED
- **Corrected Verdict:** DEFERRED_OK
- **Corrected Severity:** n/a (not a defect)
- **Reasoning:** Same as R05. The read-only config view and clone workflow were explicitly deferred from phase 6. The eval_configs page shows config metadata (name, type, instructions) in a table format — this is a partial read-only view, though not the per-type form-based view the spec describes. The spec §4.3 says "a lightweight configDetail renderer — implementer's choice." The current eval_configs page + eval_config_instruction dialog provides this at a basic level for LLM judge configs. Regardless, clone/edit is explicitly out of scope.
- **Evidence:** Phase 6 plan: `phase_6.md:23,558`. Existing partial view: `eval_configs/+page.svelte` (shows config metadata + instructions in dialog).

---

## 70a-R12: LLM Judge first in picker with "(recommended)"

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor
- **Reasoning:** The spec says "'LLM as Judge (recommended)' first." The code has `llm_judge` at position 7 of 8 in `ALL_V2_EVAL_TYPES` (registry.ts:39). The label is "LLM Judge" not "LLM as Judge (recommended)". This is a real divergence in ordering and labeling, but purely cosmetic. No RUN_NOTES or phase plan decision overrides this.
- **Evidence:** Spec: `70_builder_and_onboarding.md:76`. Code: `registry.ts:39-48` (llm_judge at position 7), `registry.ts:137` (label: "LLM Judge").

---

## 70a-R13: Type picker order/labels per spec

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor
- **Reasoning:** The spec gives a specific order (LLM judge first, then Code, then the deterministics) and specific labels ("Code — Custom Python Code eval", "Pattern Match (regex)"). The implementation uses simpler labels ("Code Eval", "Pattern Match") and a different order. These are minor cosmetic divergences. The simpler labels arguably read better.
- **Evidence:** Spec: `70_builder_and_onboarding.md:77`. Code: `registry.ts:39-48` (different order), `registry.ts:72-156` (simpler labels).

---

## 70a-R15: URL/history push on type select

- **Skeptic Verdict:** UPHELD
- **Corrected Verdict:** PARTIAL
- **Corrected Severity:** minor
- **Reasoning:** The spec says "On select: push history / update URL the SvelteKit-official way, so Back returns to the picker." The code uses local state (`selected_v2_type = type`) with no URL update (line 158-159). A manual "Back" button exists (line 519-525) that resets state. Browser Back will navigate away from the page entirely. This is real but minor — the manual Back button serves the primary use case (going back to picker from the form).
- **Evidence:** Spec: `70_builder_and_onboarding.md:79`. Code: `+page.svelte:158-159` (no pushState/goto).

---

## 70a-R53: Test-run available for ALL types incl. LLM judge

- **Skeptic Verdict:** REFUTED_INTENTIONAL
- **Corrected Verdict:** NOT_DEFECT (intentional design)
- **Corrected Severity:** n/a
- **Reasoning:** The spec §1 says "test-run is not per-component... every future type gets test-run for free." However, the phase 6 plan (line 91) explicitly says the test-run panel is "Only shown for V2 types" — and the LLM judge, while technically a V2 type, has a completely separate form component (`LlmJudgeForm`) and save path in the architecture. The phase 6 plan treats LLM judge as a special case (lines 82-93): its legacy workflow was extracted into a sub-component, keeping its existing model-picker + eval_steps + comparison-based calibration flow. The LLM judge's "test" mechanism is the existing "Compare Judges" calibration workflow (run against golden dataset), which is far more meaningful than a single-input test-run. The exclusion is intentional architecture, confirmed by `phase_6.md:91` and the signoff item at line 548 ("one LLM-backed type") which refers to `code_eval` (the only LLM-backed type that uses the V2 test panel — via `requiresTrust`).
- **Evidence:** Phase 6 plan: `phase_6.md:91` ("Only shown for V2 types" — in context of V2 types that go through the generic form path, not the LLM judge legacy path). Code: `+page.svelte:205` (`can_submit_v2 = selected_v2_type && !is_llm_judge`). Existing LLM judge calibration: `eval_configs/+page.svelte` (Compare Judges flow).
