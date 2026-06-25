---
status: complete
---

# Implementation Plan: Evals V2 — Create-Flow UI Polish

Dependency-ordered checklist (follows `architecture.md §12`). Detail lives in
`functional_spec.md`, `architecture.md`, and `design_specs/` — not restated here. Frontend-only
**except the final Phase 10 (D16)**, which adds a small backend validation + one response field.
The coding agent writes `phase_plans/phase_N.md` before each phase. Run the web check suite
(`npm run check`, `lint`, `format_check`, `test_run`, `build`) before each phase's code review;
no OpenAPI schema change is expected before Phase 10. Phase 10 additionally runs the Python check
suite and regenerates the OpenAPI client.

## Phases

- [x] **Phase 1 — Registry foundation.** Add additive `V2EvalTypeMetadata` fields (`recommended`,
  `tags`, `pageTitle`, `pageSubtitle`, `explainer`, optional `example`); set the locked content
  (functional spec §1 cards/descriptions/tags, §2 titles); drop the qualifier suffixes from
  `label`. Update `registry.test.ts` invariants. Unblocks all later phases. (arch §1)

- [x] **Phase 2 — Select Eval Type screen.** New `eval_type_hero`, `eval_type_row`,
  `eval_type_tags`; rebuild `create_eval_config/+page.svelte` as recommended-hero + "All judge
  types" list, data-driven from `ALL_V2_EVAL_TYPES`; new header copy; drop the secondary heading
  and the "Read the Docs" sub-subtitle. (arch §2, design_specs/select_screen.md)

- [x] **Phase 3 — Container shell + titles + intro.** Per-page `pageTitle`/`pageSubtitle` in the
  `[eval_config_type]` route; `/run`-style two-column shell in `eval_config_builder`; remove the
  secondary-title block (fixes indent globally); new `eval_type_intro` at the top of the left
  column. (arch §3)

- [x] **Phase 4 — Trust modal + bugs.** New trust-modal copy + large warning icon (no yellow
  box); dismiss-on-trust (fire-and-forget) so the Test Run pane shows Running on the page; fix B1
  (reset `create_evaluator_loading` when deferring to confirm/trust dialog). Regression tests.
  (arch §4, §8-B1)

- [x] **Phase 5 — Test Run pane (extraction + states).** Extract `eval_test_run_pane` (builder
  stays orchestrator, pane is presentational + event-driven); implement the 5 states;
  `test_run_input_card` (selected + 2 quick-picks, 2-line input+output + tooltips);
  `test_run_browse_dialog` (wide, no search, input+output, "Add manual example");
  `manual_example_dialog` (ephemeral run); `reference_data_field` (property-row → JSON modal).
  Auto-select first run. (arch §5, design_specs/test_run_sidebar.md)

- [x] **Phase 6 — Code Judge form + LLM cards.** Code form: standard `header_only`+`inline_action`
  Score Function header (subtitle + tooltip + "More Examples"); remove the footer paragraph;
  consolidate the redundant top badge/line. LLM judge: shrink model + algorithm cards ~40% with
  smaller icons. (arch §6, functional spec §5/§7)

- [x] **Phase 7 — Deterministic forms I (shared parts + value-expression family).** New
  `form_parts`: `form_section`, `disclosure_radio_group`, `output_value_field`. Redesign
  `exact_match`, `pattern_match`, `contains` (info via intro, section titles, progressive
  disclosure replacing nested radios, relabeled "Output Value to Compare" + Jinja tooltip).
  Preserve each form's `getProperties()`/`validate()` + on-blur checks. (arch §7, functional
  spec §8)

- [x] **Phase 8 — Deterministic forms II.** Redesign `set_check` (tag-input set + comparison
  mode), `tool_call_check` (expected-tools + match mode + on_unexpected_tools), `step_count_check`
  (count type + bounds) using the same `form_parts` and principles. (arch §7, functional spec §8)

- [x] **Phase 9 — Docs-link audit + final polish.** Audit/remove non-salient/dead docs links
  (B2), incl. `[eval_id]/+page.svelte` `docs_link()`; verify liveness where possible. Final
  cross-flow consistency pass (headings, spacing, copy) against the Kiln design guide. (arch §8-B2)

- [ ] **Phase 10 — Test-pane score-range validation (D16).** *The one backend phase.* Extract the
  per-rating-type range checks from `EvalRun.validate_scores`
  (`libs/core/kiln_ai/datamodel/eval.py:531-587`) into a shared
  `validate_scores_against_output_scores(scores, output_scores)`; refactor `EvalRun` to call it (no
  behavior change — existing tests stay green). Call it from `test_v2_eval`
  (`app/desktop/studio_server/eval_api.py:1037-1083`) on a **non-skipped** adapter result and
  return any out-of-range problems on a new optional `TestV2EvalResponse.score_range_errors`
  (scores still returned so the pane can show them). In `eval_config_builder.run_test`, fold those
  errors into the score warning and force `test_has_valid_run=false` so Save is gated through the
  confirm modal — same UX as a shape mismatch. Regenerate the OpenAPI client; add core + API +
  frontend regression tests. Run the Python check suite alongside the web suite. (arch §13)

## Notes

- Phases 1–3 are low-risk and unblock the rest; **4, 5, 7** carry the most risk.
- Decisions baked in (see `functional_spec §13`): type-appropriate titles (D1); all six forms
  full redesign (D2); adopt select tags (D3); design-bot wireframes are layout-only (D4);
  manual examples ephemeral; trust fire-and-forget; Test Run pane fully extracted.
- Use Claude's `/frontend_design` skill for the visual-design-heavy phases (2, 5, 7, 8).

## Out of scope (see functional_spec §12)

Eval engine / save contract (beyond the Phase 10 / D16 score-range extraction); typed score badges
& fail-loud view binding; view/run-result/comparison surfaces; copilot/eval-builder/questionnaire;
persisting manual examples; backend changes (other than the Phase 10 / D16 validation).
