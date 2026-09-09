# Cluster A Skeptic Verification: V1-vs-V2 Creation Paths (K Decisions)

## Summary Conclusion

The K decisions (K.1, K.2, K.3) from `components/15 section 8` are **unambiguously specified** -- "no new V1 EvalConfig records are created via any path" (section 8.2). However, they were **never decomposed into any implementation phase**. The phase 6 plan (step 7 + step 10d) explicitly instructs the LLM judge form to produce V1 payload shapes. The copilot path (`copilot_api.py`) was never touched by evals_v2 commits at all. This is a genuine spec-fidelity gap: the spec requires V2-only creation, the implementation deliberately keeps V1 creation for LLM judge paths, and the `v1_to_v2_prompt_template()` wrapping function was never built.

This is NOT an intentional post-spec user override (no RUN_NOTES entry, no git evidence of deliberate override). It is fidelity lost during phase decomposition -- the spec's section 11 "sub-task 8" was never given a home in the actual Phase 1-6 plan.

---

## Per-Finding Verdicts

### 15-R41 — K.1 manual create_eval_config endpoint

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** CONTRADICTED
- **Corrected severity:** major
- **Reasoning:** The spec (component 15, section 8.1) explicitly states the endpoint "internally constructs V2-shaped EvalConfig: `EvalConfig(config_type='v2', properties=LlmJudgeProperties(...))`." The code at `eval_api.py:948-956` passes `request.type` and `request.properties` through directly. When the frontend sends `type: "g_eval"` or `"llm_as_judge"`, a V1 config is created. The phase 6 plan (step 10d) explicitly instructs this V1 behavior for "legacy types" -- this is a decomposition error, not an intentional post-spec override.
- **Evidence:** `eval_api.py:949` (`config_type=request.type`); phase 6 step 10d ("Legacy types: POST with existing payload shape"); component 15, section 8.2 ("no new V1 EvalConfig records are created via any path").

### 15-R42 — K.2/K.3 Copilot path constructs V2 EvalConfigs

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** CONTRADICTED
- **Corrected severity:** major
- **Reasoning:** The spec (component 15, section 8.3) says "`copilot_api.py:337-340` is updated to construct V2 EvalConfigs from V1-shaped Copilot responses." The code at `copilot_api.py:337-347` still creates `EvalConfigType.llm_as_judge` with raw dict properties. `git log scosman/evals_v2 -- copilot_api.py` shows no evals_v2-related modification. The Copilot path was never included in any phase plan.
- **Evidence:** `copilot_api.py:340` (`config_type=EvalConfigType.llm_as_judge`); `copilot_api.py:328` (`eval_set_filter_id=eval_set_filter_id` -- V1 filter); no evals_v2 commits touching this file; no phase plan references K.2.

### 15-R48 — spec_builder should produce only V2 EvalConfigs

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor
- **Reasoning:** `spec_api.py:115-126` creates Evals with `eval_set_filter_id` (V1 filter). However, spec_api does NOT directly create EvalConfigs -- those are created later via the `create_eval_config` endpoint. The spec_api creates the Eval container, and the EvalConfig creation is separate. The issue is that the Eval itself uses V1 `eval_set_filter_id` rather than V2 `eval_input_filter_id`, but per spec section 8.2 table, the "Manual path" is allowed to use `eval_set_filter_id`. The spec_builder is a manual-path flow (spec creation leads to manual eval config creation). The real gap is the absence of `eval_input_filter_id` support in `CreateEvaluatorRequest` (covered by R19).
- **Evidence:** `spec_api.py:121` (`eval_set_filter_id=eval_set_filter_id`); spec section 8.2 table shows Manual path uses `eval_set_filter_id`; `CreateEvaluatorRequest` at `eval_api.py:171` only has `eval_set_filter_id: DatasetFilterId` (no `eval_input_filter_id` option).

### 21-R38 — v1_to_v2_prompt_template() wrapping function not implemented

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** MISSING
- **Corrected severity:** major
- **Reasoning:** The spec (component 21, section 10.1-10.3) defines a complete `v1_to_v2_prompt_template()` function that wraps V1 `eval_steps` + `task_description` into a V2 Jinja2 template. No such function exists anywhere in the codebase. This is the implementation-level dependency for K.2 (Copilot path V1-to-V2 translation). Since K.2 was never phased, this is correctly MISSING.
- **Evidence:** `grep -rn "v1_to_v2" /Users/scosman/Dropbox/workspace/kiln_new/` returns no results outside spec files. No phase plan references this function.

### 21-R39 — LLM judge create form produces V1 legacy configs

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** CONTRADICTED
- **Corrected severity:** major
- **Reasoning:** The spec (component 21, section 10.3-10.4) says V1 fields "must be wrapped into a complete V2 prompt_template." The code at `llm_judge_form.svelte:42-44` returns `"g_eval"` or `"llm_as_judge"` as config_type, and `llm_judge_form.svelte:35-39` returns `{ eval_steps, task_description }` as V1 properties. The create container (line 347) uses these directly. This produces V1 configs, contradicting the spec's K.1 requirement. The phase 6 plan explicitly designed this behavior (step 7 + step 10d).
- **Evidence:** `llm_judge_form.svelte:42-44` (`getConfigType()` returns `selected_algo` which is `"g_eval"` or `"llm_as_judge"`); `create_eval_config/+page.svelte:347` (`config_type = llmJudgeFormComponent.getConfigType() ?? "llm_as_judge"`); phase 6 step 10d.

### 21-R40 — required_var=[] for wrapped templates

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** MISSING
- **Corrected severity:** minor (dependent on 21-R38)
- **Reasoning:** This is a detail of the wrapping function that doesn't exist. Since `v1_to_v2_prompt_template()` was never built (21-R38), the `required_var` derivation is also necessarily missing. Severity is minor because it is purely a consequence of the parent gap.
- **Evidence:** Dependent on 21-R38 -- no wrapping function, no required_var derivation.

### functional-arch-crosscut-R01 — Copilot path must produce V2 EvalConfigs

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** CONTRADICTED
- **Corrected severity:** major
- **Reasoning:** Duplicate of 15-R42. The copilot path at `copilot_api.py:340` creates `EvalConfigType.llm_as_judge`, contradicting the spec's "only V2 EvalConfigs" requirement.
- **Evidence:** `copilot_api.py:340` (`config_type=EvalConfigType.llm_as_judge`).

### functional-arch-crosscut-R02 — Manual LLM judge creation must produce V2 EvalConfig

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** CONTRADICTED
- **Corrected severity:** major
- **Reasoning:** Duplicate of 15-R41 + 21-R39. The manual LLM judge UI produces V1 configs. The frontend form returns V1 types, the backend endpoint passes them through.
- **Evidence:** `llm_judge_form.svelte:43` (returns V1 config type); `eval_api.py:949` (passes through unchanged).

### functional-arch-crosscut-R19 — CreateEvaluatorRequest must support eval_input_filter_id

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor
- **Reasoning:** `CreateEvaluatorRequest` at `eval_api.py:171` only has `eval_set_filter_id: DatasetFilterId` (required, no None). No `eval_input_filter_id` field. However, this only matters for the Copilot path (which per the spec section 8.2 table uses `eval_input_filter_id`). The Manual path correctly uses `eval_set_filter_id`. Since the Copilot V2 migration (K.2) was never phased, this is a companion gap. The REST API does not support creating V2 EvalInput-backed Evals, but the Python library does.
- **Evidence:** `eval_api.py:158-182` (no `eval_input_filter_id` in `CreateEvaluatorRequest`); spec section 8.2 table (Copilot uses `eval_input_filter_id`).

### functional-arch-crosscut-R30 — Copilot Eval should use eval_input_filter_id

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor
- **Reasoning:** `copilot_api.py:328` sets `eval_set_filter_id` (V1 TaskRun filter). Per spec section 8.2, the Copilot path should use `eval_input_filter_id`. This is a companion issue to R01/15-R42 (the Copilot path was never migrated to V2). Downgraded because the Copilot path still works correctly via the V1 flow -- it is functionally operational, just not using the V2 data model.
- **Evidence:** `copilot_api.py:328` (`eval_set_filter_id=eval_set_filter_id`); spec section 8.2 table.

---

## Overall Conclusion

The V2 creation-path migration (K decisions K.1, K.2, K.3) was **not implemented**. The spec is unambiguous: section 8.2 says "no new V1 EvalConfig records are created via any path." The implementation deliberately keeps V1 creation for LLM judge configs (both manual UI and Copilot paths). The `v1_to_v2_prompt_template()` wrapping function does not exist. This is not a case of "runs fine under legacy dispatch" -- while V1 configs do execute correctly via the legacy GEval adapter (D.5 is met), the creation-shape requirement is clearly violated. The gap traces to a decomposition failure: the spec's "sub-task 8" (section 11) was never assigned to any of the 6 implementation phases.
