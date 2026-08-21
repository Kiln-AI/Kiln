# Cluster B — g_eval function_calling structured-output mode

## Finding: 21-R19

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** CONTRADICTED
- **Corrected severity:** minor
- **Reasoning:** The spec clearly states `g_eval=False` should allow function_calling ("broadens model support") while `g_eval=True` must disallow it. The code unconditionally disallows function_calling for both modes. However, the real-world impact is minor: (1) When function_calling is disallowed and the model's preferred mode is function_calling, `default_structured_output_mode_for_model_provider()` falls through to the caller-supplied default of `json_schema` (ml_model_list.py:8004-8008). (2) Every provider that supports function_calling also supports json_schema — there is no model in the registry that ONLY works via function_calling. (3) The V1 `g_eval.py:275` already unconditionally disallows function_calling for both V1 types (g_eval AND llm_as_judge) with comment "G-eval expects JSON, so don't allow function calling modes". The V2 code replicated V1's conservative behavior. (4) `build_llm_as_judge_score` works identically on dicts parsed from either json_schema or function_calling — no quality degradation. This is a conservative-but-acceptable choice, not a behavioral defect. No evidence in RUN_NOTES or git history of an explicit user decision to diverge; the code simply carried forward V1's blanket restriction.
- **Evidence:**
  - Spec: component 21 §4.1 table row "function_calling: Allowed" for g_eval=False; §1.1 field semantics: "`False` = structured-output judge (function_calling allowed, no logprobs)"; component 40 line 144: "False: pure llm_as_judge; no logprobs; function_calling allowed (broadens model support)."
  - Code: `v2_eval_llm_judge.py:138-146` — unconditional `disallowed_modes=[StructuredOutputMode.function_calling, StructuredOutputMode.function_calling_weak]`
  - V1 precedent: `g_eval.py:275-278` — same unconditional disallow with comment "G-eval expects JSON"
  - Fallback path: `ml_model_list.py:8003-8008` — when mode is disallowed, returns `default` param (`json_schema`), which all providers support
  - Original commit: `e69e6aee5` introduced the disallow unconditionally; never changed in subsequent commits (`5efc62653`, `e587e43c3`)
  - No RUN_NOTES entry or explicit user decision recorded

## Finding: 40-R18

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** CONTRADICTED
- **Corrected severity:** minor
- **Reasoning:** Same underlying issue as 21-R19 (same code path). Spec 40 §3.1 line 144 says "False: pure llm_as_judge; no logprobs; function_calling allowed (broadens model support)." The code does not conditionally allow it. This is a duplicate observation of 21-R19 in a different spec component. Same downgrade rationale applies: no model requires function_calling-only, json_schema fallback works universally, V1 precedent established this pattern, no quality/compatibility degradation in practice.
- **Evidence:**
  - Spec: `components/40_template_and_extraction.md` line 144
  - Code: `v2_eval_llm_judge.py:138-146` (same as 21-R19)
  - All evidence from 21-R19 applies identically
