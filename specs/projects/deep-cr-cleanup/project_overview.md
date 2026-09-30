---
status: complete
---

# Deep CR Cleanup

Address the moderate and mild findings from the evals_v2 deep code review (`reviews/projects/evals_v2/`) that were NOT covered by the four critical-fix commits (tool_call_check `expected_args`, V1 coexistence tests, Issue 1 V2 fresh-gen, Issue 2 EvalInput execution).

This overview was assembled interactively from a batch-by-batch triage of the backlog. Each item below records the user's decision (FIX / SKIP / chosen option). **Triage is complete — all 7 batches decided.** It is the `project_overview.md` for a `/spec new project` spec; a clean agent implements it later. Note: one item was already implemented outside this spec (the RAG punt) — the implementation plan therefore includes a **Verification phase** that confirms it matches its goal rather than re-doing it (see "Already-completed work" below). Everything else, including 7.1, is normal FIX work the spec covers.

## Implementation guidance (for coding agents)

These decisions were made during a high-level deep-CR walkthrough. **When you implement a decision, you will read the actual code with far more context than the deep CR or the triage had.** Use it:

- **Push back is allowed and expected — after reading the code.** If implementing a decision as written would cause a quality regression, break an invariant, fight the existing design, or is simply wrong given what the code actually does, **stop and raise it** instead of forcing the change through. Do not degrade code quality just to satisfy a line item.
- A decision here is a *direction*, not a mandate to regress. The bar is still "very high code quality" — if the line item and that bar conflict, the bar wins and you flag the conflict.
- Surface the pushback concisely (what the decision said, what the code actually shows, why the change would hurt, your recommended alternative) and let the human re-decide.
- This does **not** license silently skipping work you simply find tedious — push back only on genuine quality/correctness grounds, with the code as evidence.

## Scope decisions

_(populated as batches are triaged — see the walkthrough)_

### Already-completed work — covered by a Verification phase (do NOT re-implement)
The **RAG punt** was already implemented outside this spec's coding work. The implementation plan includes a dedicated **Verification phase** whose job is to confirm it matches its stated goal, and to file any gap as follow-up — **not** to re-implement it. (This is the only already-done item; everything else in this spec, including 7.1, is normal implementation work.)

**RAG judge templates + continuous scoring** — **already done and merged** on `scosman/evals_v2` (removal `5efc626`, SHA-record follow-up `74154c0`). Verify the removal landed cleanly:
- V1 scoring byte-identical to `main` (A0.1); V2 `llm_judge` now discrete (`allow_float_scores=False`); strict `build_llm_as_judge_score` restored (raises on a non-mapping value).
- No RAG references remain across `libs` / `app` / `specs`; specs annotated as punted; `specs/projects/rag_templates/project_overview.md` exists and records the removal SHA.
- Re-check Batch-1 #2's target (`_filter_output_to_score_keys`) — it may have been removed with the RAG templates.

### Batch 1 — Correctness bugs — ✅ SIGNED OFF (decisions locked; implementation pending)
- **FIX** `v2_eval_helpers.py` extract/`required_var`: treat `None` (not just `Undefined`) as skip, per spec (missing reference data → clean skip, not garbage to the judge).
- **FIX** `v2_eval_llm_judge.py:180-197` `_filter_output_to_score_keys`: when no output keys match score names, raise a clear "no recognized score fields (expected X, got Y)" error instead of silently passing the unfiltered output through. *(Re-check after the RAG punt — this function may be removed with the RAG templates.)*
- **FIX** `eval.py` `validate_output_fields` V1 branch: guard `output is not None` (V1 EvalRun with `output=None` currently passes validation → later `AttributeError`).
- **SUPERSEDED by the RAG punt** `scoring_utils.py` `build_llm_as_judge_score`: no `strict` flag. The RAG-punt task reverts V2 `llm_judge` to discrete scoring, so V1 and V2 both reuse the original pristine strict scorer — no flag, no fork. Tracked under the RAG-punt task (see remediation tracker §2), not here.
- **DOC-ONLY (keep code as-is)** `code_eval` `_validate_scores` (`v2_eval_code_eval.py:104-109`): keep the strict exact-key-match (fail loudly on wrong keys); the implementation intentionally diverges from the spec's lenient (missing→None / extra→ignored) rule. Update `components/27 §2.2` to record that strict validation is the chosen Kiln behavior.
- **DROPPED (non-issue)** `test_v2_eval` "missing `ValidationError`": `request.properties` is typed `V2EvalConfigProperties` (FastAPI → 422 on malformed body), and pydantic v2 `ValidationError` subclasses `ValueError` so the existing `except ValueError` already catches any internal construction error → 400. No change.

### Batch 2 — API consistency (Phase 6) — ✅ DECIDED
- **FIX** (2.1) Trust endpoints typed response (`eval_api.py:1737,1756`): replace `dict[str, bool]` with a named `CodeEvalTrustResponse(BaseModel){ trusted: bool }` so the OpenAPI/TS contract is a closed object, not an open bool-map. Regen the web_ui schema.
- **FIX — option (a)** (2.2) V2 read-endpoint handling: keep the existing single-resource→400 / list-aggregation→skip split (it's correct), and **only fix the two leaky 400 messages** in `get_eval_progress` (`:1188`) and `get_eval_config_score_summary` (`:1259`) — replace "This eval does not have a V1 eval set filter" with a type-agnostic "This endpoint isn't supported for this eval type." No behavior change to the list endpoints (`eval_results_summary`, `run_config_eval_scores`).
- **FIX** (2.3) `create_eval_config` V2 validation asymmetry (`eval_api.py:927-932`): instead of surfacing a raw Pydantic `ValidationError` string for V2 types, return a clean 400 with a message in the same shape as the V1 missing-field error. Add a quick test.
- **SKIP** (2.4) `dev_server.py:25` `freeze_support()`: in-branch but a genuine no-op (dev is never frozen) and redundant — `sandbox_worker.py:110` spawns via an explicit `get_context("spawn")`, independent of the global default. Harmless; leave it.
- **SKIP** (2.5) `dev_server.py:16,26` `set_start_method("spawn")` ordering: moot for the same reason (explicit spawn context; `make_app()` doesn't spawn at import). Not a bug.
- **FIX** (2.6) Lazy imports in trust endpoints (`eval_api.py:1738,1757`): move `project_from_id` and `v2_eval_code_eval` imports to module top-level (neither is slow / avoiding an already-loaded module). Guardrail: verify no import cycle; if one exists, document instead.
- **SKIP** (2.7) POST endpoints return 200 not 201 (`eval_api.py:910-952`): pre-existing convention across the whole file; fixing one endpoint creates new inconsistency. Out of scope for this branch's CR.

### Batch 3 — code_eval & security hardening (Phase 5) — ✅ DECIDED
- _(Phase 5 M1 `_validate_scores` exact-key-match = already closed as Batch 1 #5 DOC-ONLY — keep strict, document in `components/27 §2.2`. Not re-decided here.)_
- **FIX** (3.1) `_spawn_lock` too narrow (`sandbox_worker.py:112-115`): serialize the **full** code_eval execution per spec §4.6/§5.1, not just `p.start()`. Implement via a module-level `asyncio.Lock` around the `await run_in_executor(...)` in `CodeEvalAdapter.evaluate()` (so waiting code_evals suspend as coroutines rather than blocking executor threads for up to 300s), and **keep** the existing narrow `threading.Lock` around `p.start()` for the PyInstaller spawn race (#7410).
- **FIX** (3.2) Timeout input min/max (`code_eval_form.svelte:161-168`): add `min={1} max={300}` so invalid values give immediate client-side feedback instead of a save-time server error.
- **FIX** (3.3) Trust dialog wording (`create_eval_config/+page.svelte:714`): **remove the reassurance entirely** — drop "Code evals execute Python in a sandboxed subprocess. While basic safeguards are in place, …". Do **not** describe the execution method at all (no "sandboxed"/"isolated"/"subprocess"/"safeguards"). The dialog's only question is "do you trust this code to run on your machine?" — we must not soften the risk by implying any protective mechanism. Keep/strengthen the plain "runs arbitrary Python code on your machine" warning.
- **FIX** (3.4) `five_star` docstring (`eval_helpers.py:92-101`): docstring says "clamped" but the code raises `ValueError`; correct the docstring to match the (correct) raising behavior.

### Batch 4 — Frontend type-safety & UI (Phase 7) — ✅ DECIDED
- **FIX** (4.1) `formatEvalConfigName` dead ternary (`formatters.ts:340-345`): collapse the identical V2 compact/non-compact branches to a single expression.
- **FIX** (4.2 + 4.4) `any` / `SvelteComponent<any>` on the V2 form component (`create_eval_config/+page.svelte:174-175` + `registry.ts:52-56`): define a shared interface for the eval-type form's imperative API — **name it `EvalTypeFormApi`** (better than `V2FormComponentAPI`; the implementer may refine if a clearer name fits) — `{ getProperties(): V2EvalConfigProperties; validate?(): string | null }`. Type the registry's `createFormComponent` against it, narrow at call sites, and remove the `eslint-disable`s. (Svelte 4 typing is awkward — a cast at the `bind:this` site may be needed.)
- **SKIP** (4.3) LLM-judge test asymmetry: confirmed intentional by code — `is_llm_judge` renders its own `<LlmJudgeForm>` (V1-style configure→save→run-eval); the inline "Test Your Judge" panel is only for deterministic types (instant, no model call). No doc needed.
- **FIX** (4.5) Remove dead `"value_expression"` union member in `exact_match_form.svelte` (no UI option offers it).
- **FIX** (4.6) Dedupe the 7× repeated `as`-cast property extraction in result components into a shared `extractV2Props<T>(eval_config, expectedType)` type-guard util.
- **FIX** (4.7) `tool_call_check_result.svelte`: import `components["schemas"]["ToolCallSpec"]` instead of a local mirror type.
- **SKIP** (4.8) `set_check_form.svelte` imperative-null vs reactive-derive tension — benign (textarea hidden when source is `reference_key`).
- **SKIP** (4.9) `model_name`/`provider_name` (display) vs `combined_model_name` (ID) naming — matches the existing `AvailableModelsDropdown` convention; renaming spreads churn.
- **SKIP** (4.10) Unreachable `|| eval_config_type` fallback in `eval_config_to_ui_name` — harmless; `satisfies` already guarantees coverage.

### Batch 5 — Data-model semantics & spec alignment (Phases 1–2) — ✅ DECIDED
_Already handled / moot (not re-decided): EvalRun `output is not None` guard = Batch 1 #3; `required_var`/`extract_value` None-handling = Batch 1 #1; Phase-2 `stored_trace` type = moot (field deleted by Issue 1)._

- **DOC-ONLY** (5.1) `evaluation_data_type` default (`eval.py:733-734`): the code default `EvalDataType.final_answer` is **better** (a V1 Eval on disk that omits the field loads as its true V1 behavior, not ambiguous `None`). Keep the code; update spec `15_v1_v2_coexistence.md:215` to match + record the back-compat rationale. (Confirm `final_answer` is the correct V1-equivalent when documenting.)
- **FIX** (5.2) `eval_adapter_from_type` (`registry.py:27`): rename to `legacy_eval_adapter_from_type` to signal the legacy path; make the V2-branch error point at `v2_eval_adapter_from_config`. Mechanical rename across call sites.
- **FIX — TODO-gate** (5.3) reference_data unpopulated for TaskRun sources → reference_key/`required_var` evals silently skip. In V2.0 no wired source populates reference_data **from the UI**, so any UI affordance that selects a `reference_key`/reference_data source would always-skip. **We must not ship UI we can't populate.** Add `TODO` comments at every UI entry point that offers a reference_key/reference_data source (e.g. the `source` selector in `exact_match_form.svelte`, `set_check_form.svelte`, and any other eval-type form exposing it). The TODO must say: either wire reference_data population into the UI, or remove the affordance, **before ship**. CI's no-TODO-on-main rule makes this a hard pre-ship gate. The SDK/code path keeps working — this is a UI-completeness gate only, not an SDK restriction. (Implementer: grep all eval-type forms for `reference_key`/reference_data source options and tag each.)
- **FIX** (5.4) Remove dead `except SyntaxError: pass` in `CodeEvalProperties.validate_code` (`eval.py:222-223`).
- **→ Batch 6** (5.5) Keep `skipped_reason` as `str` (forward-compat, intentional); add a test asserting runner paths emit valid `SkippedReason` values.
- **FIX-light** (5.6) Clarify the `dataset_id`/`eval_input_id` mutual-exclusivity error message for V1 callers (`eval.py:367-369`).
- **SKIP** (5.7) `EvalInputFilter` mirroring `DatasetFilter` — by design per spec §4.2; already documented.
- **FIX** (5.8) Replace the fragile double-`get_args` `_V2_PROPERTY_TYPES` unwrap (now in `base_eval.py`) with an explicit property-types tuple defined in `eval.py` beside the `V2EvalConfigProperties` alias.
- **FIX-light** (5.9) Cache `output_scores` at adapter/runner init so `build_binary_scores` doesn't call `parent_eval()` (disk I/O) per item (`v2_eval_helpers.py:8-18`) — implementer to confirm the hot path.
- **→ Batch 6** (5.10) Verify the coexistence-tests commit (`42050a2`) covers a V1-EvalConfig-with-`properties.type:"exact_match"` round-trip (discriminated-union misroute guard); add it if missing.

### Batch 6 — Test quality & dedup (Phases 9a/9b) — ✅ DECIDED (test-internal; user delegated, took recommendations)
_Already resolved: Phase-9a critical (`never`+`expected_args` test) = `7e73c3f`; Phase-9b critical (API V1-coexistence test) = `42050a2`; Phase-9b rag_judge_templates smoke-test mild = MOOT (file deleted by RAG punt)._

- **FIX** (6.1) Extract duplicate `StubV2Eval`/`SkippingStubV2Eval` (`test_v2_dispatch_and_contract.py` + `test_eval_runner.py`) to a shared conftest/helper.
- **FIX** (6.2) Dedupe overlapping dispatch tests + exact dupes in `test_registry.py`. **Coordinate with 5.2** (the `legacy_eval_adapter_from_type` rename + V2-error change updates these).
- **FIX** (6.3) Shared conftest fixture factory for the `_make_config`/`_inp` boilerplate duplicated across all 6 deterministic matcher test files.
- **FIX (verify+fill)** (6.4) Model-layer V1 coexistence — confirm `42050a2` covers, then add gaps: (a) V1 EvalRun with new optional fields → `None`, (b) V1 config through the legacy runner end-to-end, (c) V1 EvalConfig `config_type=None` load+run. **Absorbs 5.10** (V1-dict-with-`properties.type:"exact_match"` misroute round-trip). *Highest-value item — the A0.1 V1-regression guard.*
- **FIX** (6.5) Convert `test_g_eval_raises_when_provider_lacks_logprobs` from `run_until_complete` to `@pytest.mark.asyncio` (verify it still exists post-RAG-revert).
- **SKIP** (6.6) create_eval_config page test heavy mocks — inherent to page-level integration; just don't grow the mock count.
- **FIX-light** (6.7) Extend exact_match's "score with vs without eval_config" renderer-test pattern to the other 7 result renderers.
- **FIX** (6.8) `test_nothing_persisted` — assert against the actual data-model directory, not an unrelated `tmp_path` (avoid a vacuously-passing test).
- **SKIP** (6.9) Direct `_coerce_to_set` tests — leave as-is (public `evaluate()` covers; removing risks losing edge coverage).
- **SKIP** (6.10) Parametrize matcher pass/fail tests — broad mechanical churn for style; low value.
- **FIX** (6.11) sandbox_worker timeout test `sleep(60)`/2s → `sleep(10)`/1s (faster on failure, same margin).
- **FIX-light** (6.12) Add a provenance README to `test_g_eval_data/` (pickle fixtures are opaque).
- **FIX-light** (6.13) Parametrize the 8 repetitive `v2_eval_api.test.ts` error-path tests with `it.each`.
- **FIX** (6.14) `registry.test.ts` — derive the count from the expected-types array instead of hardcoded `toHaveLength(8)`.
- **FIX** (5.5, carried-in) Add a test asserting runner paths emit valid `SkippedReason` values.

### Batch 7 — Dependencies & trivial cleanup (Phase 8) — ✅ DECIDED
- **FIX** (7.1) Remove the redundant `codemirror` umbrella package (`package.json:60`) and re-resolve the lockfile (`npm install`). Verified during triage: the editor uses only the 5 granular `@codemirror/*` packages (dynamically imported in `code_editor.svelte`, pinned at `package.json:52-56`); the umbrella is imported nowhere in `src`, so removing it drops ~4 unused transitive deps (`@codemirror/autocomplete`, `lint`, `search`, `crelt`) without touching the working editor.
- **SKIP** (7.2) ~30 unrelated `"peer": true` lockfile markers — npm metadata reorg noise; 7.1's `npm install` re-resolves the lockfile anyway.

## Out of scope
- The 3 critical themes (already fixed & committed on `scosman/evals_v2`).
- Findings rendered moot by the critical fixes (e.g. `EvalJob.stored_trace` type — field deleted).
