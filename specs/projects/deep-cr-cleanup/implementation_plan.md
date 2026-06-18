---
status: complete
---

# Implementation Plan: Deep CR Cleanup

For this remediation project the detailed `project_overview.md` doubles as the functional + architectural spec — every item carries its behavior, file refs, and rationale — so we go straight to phasing. **Each phase is one small, single-concern commit** (coding agent → spec-aware CR → commit). Item IDs (e.g. `2.1`, `6.4`) reference `project_overview.md`.

**Cross-cutting rules (every phase):**
- Follow the overview's "Implementation guidance" — read the code; push back rather than regress quality to satisfy a line item.
- Leave **no** `TODO`s except the deliberate 5.3 reference-data UI gates (an intentional pre-ship gate).
- Get the project's automated checks green before committing. (The eval test suite needs the sandbox disabled — the logging fixture writes to `~/.kiln_ai/logs/`.)
- Tests for a code change live in that change's phase; the standalone test-hygiene phases cover coverage/dedup work not tied to one fix.

## Phases

- [x] **Phase 1 — Verify the already-done RAG punt.** Verification only (independent; run first). Execute the "Already-completed work" checklist (V1 == `main` A0.1, V2 discrete, strict scorer restored, no RAG refs, specs punted, `rag_templates` overview + SHA). Resolve Batch-1 #2's open question: does `_filter_output_to_score_keys` still exist? (feeds Phase 2). File gaps as follow-up; do not re-implement.

- [x] **Phase 2 — Backend correctness guards.** Batch 1: 1a (`required_var`/`extract_value` treat `None` as skip), 1b (`_filter_output_to_score_keys` raise on no-match — only if it survived the RAG removal), 1c (V1 `output is not None` guard); plus 5.4 (remove dead `except SyntaxError`). + tests for each.

- [x] **Phase 3 — Rename legacy dispatcher.** 5.2 (`eval_adapter_from_type` → `legacy_eval_adapter_from_type`, clearer V2-branch error) across all call sites; + 6.2 (dedupe the now-overlapping dispatch tests in `test_registry.py`).

- [x] **Phase 4 — Data-model robustness.** 5.8 (explicit `_V2_PROPERTY_TYPES` tuple in `eval.py`), 5.9 (cache `output_scores` to drop per-item `parent_eval()` I/O), 5.6 (clarify the `dataset_id`/`eval_input_id` mutual-exclusivity error). + tests.

- [x] **Phase 5 — Reference-data UI TODO-gates.** 5.3 — add the pre-ship `TODO`s at every eval-type form exposing a `reference_key`/reference_data source (wire-or-remove before ship). SDK path untouched.

- [x] **Phase 6 — Spec doc alignment (docs only).** 1d (document intentional `code_eval` `_validate_scores` strictness in `components/27 §2.2`); 5.1 (align `15_v1_v2_coexistence.md:215` to the `final_answer` default + rationale).

- [x] **Phase 7 — Backend test hygiene.** 6.1 (shared conftest for `StubV2Eval`/`SkippingStubV2Eval`), 6.3 (shared `_make_config`/`_inp` fixture factory across the 6 matcher files), 6.5 (`run_until_complete` → `@pytest.mark.asyncio`), 5.5 (test runner paths emit valid `SkippedReason`), 6.12 (provenance README for `test_g_eval_data/`).

- [ ] **Phase 8 — V1 coexistence test guard.** 6.4 (verify `42050a2` coverage; add (a) V1 EvalRun new-fields→`None`, (b) V1 config through legacy runner e2e, (c) V1 `config_type=None` load+run; absorbs 5.10 misroute round-trip). The A0.1 regression guard.

- [ ] **Phase 9 — API: typed trust response.** 2.1 (`CodeEvalTrustResponse{trusted:bool}` replacing `dict[str,bool]`) + web_ui OpenAPI schema regen.

- [ ] **Phase 10 — API: consistency fixes.** 2.2a (de-leak the two 400 messages), 2.3 (clean V2 validation 400 + test), 2.6 (trust-endpoint imports → top-level); + 6.8 (`test_nothing_persisted` asserts the real data-model dir).

- [ ] **Phase 11 — code_eval: serialize execution.** 3.1 (full-execution serialization via a module-level `asyncio.Lock` in `CodeEvalAdapter.evaluate()`, keeping the narrow spawn-race `threading.Lock`); + 6.11 (sandbox timeout test `sleep(60)`/2s → `sleep(10)`/1s). The subtlest change — its own commit.

- [ ] **Phase 12 — code_eval: UI & doc polish.** 3.2 (timeout `min={1} max={300}`), 3.3 (trust-dialog wording — remove all method/reassurance language), 3.4 (`five_star` docstring).

- [ ] **Phase 13 — Frontend: typed form contract.** 4.2/4.4 (`EvalTypeFormApi` interface; type the registry's `createFormComponent`; narrow call sites; drop the `eslint-disable`s).

- [ ] **Phase 14 — Frontend: cleanups.** 4.1 (collapse `formatEvalConfigName` ternary), 4.5 (remove dead `"value_expression"` union member), 4.6 (`extractV2Props<T>` dedup util), 4.7 (import `ToolCallSpec` from schema).

- [ ] **Phase 15 — Frontend test hygiene.** 6.7 (extend the with/without-`eval_config` renderer pattern to the other 7), 6.13 (parametrize `v2_eval_api.test.ts` error paths), 6.14 (derive `registry.test.ts` count from the array).

- [ ] **Phase 16 — Deps.** 7.1 (remove the redundant `codemirror` umbrella; re-resolve the lockfile; confirm the editor still builds). Final pass: full project checks green across all phases.
