# Cluster F — Registry & base-class architecture deviations

## 15-R34 / 20-R07: Split registry functions

- **Skeptic verdict:** REFUTED_INTENTIONAL
- **Corrected verdict:** NOT a defect (spec stale)
- **Corrected severity:** n/a
- **Reasoning:** The split into `legacy_eval_adapter_from_type` + `v2_eval_adapter_from_config` was an explicit refactoring in Phase 3 of the deep-cr-cleanup run. Commit `712177d8c` ("rename eval_adapter_from_type -> legacy_eval_adapter_from_type; dedupe dispatch tests") makes the split intentional. The two-function design is clearer than a single function that must handle both legacy class-return and V2 instance-return patterns (since V2 needs `run_config` and `skills` arguments that legacy does not). The spec's single-function signature (`-> type[BaseEval]`) cannot accommodate V2's need to return an instantiated adapter. Functionally equivalent; architecturally an improvement.
- **Evidence:** RUN_NOTES.md Phase 3 entry; commit `712177d8c`; `registry.py:37,55`.

---

## 20-R08: _V2_ADAPTER_MAP typed as type[BaseV2EvalBridge]

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL/trivial (doc-only)
- **Corrected severity:** trivial
- **Reasoning:** The map type `dict[V2EvalType, type[BaseV2EvalBridge]]` is strictly narrower than `dict[V2EvalType, type[BaseEval]]`. Since `BaseV2EvalBridge` is a subclass of `BaseEval`, this is type-safe and actually provides stronger typing (prevents accidentally registering a non-V2 adapter). The divergence is a consequence of the intentional `BaseV2EvalBridge` introduction. No behavioral difference; a developer adding a new type would correctly infer they need `BaseV2EvalBridge` from the type annotation.
- **Evidence:** `registry.py:25`; `base_eval.py:217`.

---

## 20-R12 / 21-R42: BaseV2EvalBridge intermediate class exists

- **Skeptic verdict:** REFUTED_INTENTIONAL
- **Corrected verdict:** NOT a defect (spec stale; intentional post-spec design decision)
- **Corrected severity:** n/a
- **Reasoning:** Commit `6538d38aa` ("Unfork BaseV2Eval -> single BaseEval via thin BaseV2EvalBridge (C.11c)") explicitly introduces BaseV2EvalBridge as the resolution to a real architectural problem: V2 adapters needed fresh-output generation support via `run_task_and_eval` without duplicating infrastructure. The commit message explicitly references spec constraint C.11c, demonstrating the developer considered the spec and judged BaseV2EvalBridge to satisfy it. The class is a thin bridge (~40 lines) that wires `evaluate(EvalTaskInput)` into the shared `run_eval(TaskRun)` pipeline. It is NOT a "BaseEvalV2 fork" in the sense C.11c prohibits (a separate parallel class hierarchy). It IS `BaseEval`, just with a thin adapter pattern for the V2 `evaluate()` contract.
- **Evidence:** Commit `6538d38aa` message explicitly cites C.11c; `base_eval.py:217-254` (bridge is ~38 lines, all plumbing).

---

## 80-R13: Extensibility checklist says "subclass BaseEval directly"

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** PARTIAL/minor (doc-fidelity gap)
- **Corrected severity:** minor
- **Reasoning:** This is a real documentation gap. The spec's "how to add a new type" checklist (Section 3.1 step 4) says: "Create `JsonSchemaAdapter(BaseEval)` implementing `run_eval`." A developer following this literally would:
  1. Subclass `BaseEval` directly -- wrong; must subclass `BaseV2EvalBridge`
  2. Implement `run_eval(self, task_run, eval_job_item)` -- wrong; must implement `evaluate(self, eval_input: EvalTaskInput)`
  3. Get a type error from `_V2_ADAPTER_MAP` (expects `type[BaseV2EvalBridge]`)
  
  The friction is low (IDE/type-checker would guide them quickly), but the spec-as-documentation is inaccurate. The spec says "subclasses BaseEval directly" and "Per C.11c (no BaseEvalV2 fork)" -- the spirit of C.11c IS preserved (no separate hierarchy), but the literal instruction is wrong. The BaseV2EvalBridge introduction was intentional (see 20-R12 above), so the spec is stale, not the code.
- **Evidence:** Spec `components/80_extensibility_contract.md` Section 3.1 step 4; actual code pattern: all 8 adapters subclass `BaseV2EvalBridge` and implement `evaluate(EvalTaskInput)`, not `run_eval(TaskRun)`.

---

## 21-V01: Class named LlmJudgeEval, not LlmJudgeAdapter

- **Skeptic verdict:** REFUTED_INTENTIONAL
- **Corrected verdict:** NOT a defect (naming convention choice)
- **Corrected severity:** n/a
- **Reasoning:** The spec's code sketches used `LlmJudgeAdapter` as an illustrative name. The implementation chose `LlmJudgeEval` (following the pattern: `ExactMatchEval`, `ContainsEval`, `PatternMatchEval`, `SetCheckEval`, `ToolCallCheckEval`, `StepCountCheckEval`). This is a consistent project-wide naming convention (`*Eval` suffix for all V2 adapters). The `*Adapter` name only ever existed in the spec document (commit `cd56926bc` = "Spec for evals v2"), never in implementation code. The naming choice is coherent and does not violate any behavioral contract. Spec names in code sketches are illustrative, not normative.
- **Evidence:** `v2_eval_llm_judge.py:76`; all 8 V2 adapter classes use `*Eval` suffix; `LlmJudgeAdapter` exists only in spec prose (git log -S confirms).

---

## Summary

| Finding | Verdict | Impact |
|---------|---------|--------|
| 15-R34 / 20-R07 (split functions) | REFUTED_INTENTIONAL | Spec stale; code is an intentional improvement |
| 20-R08 (map type annotation) | UPHELD_DOWNGRADE trivial | Cosmetic type narrowing; consequence of intentional bridge |
| 20-R12 / 21-R42 (BaseV2EvalBridge exists) | REFUTED_INTENTIONAL | Explicit post-spec design decision citing C.11c |
| 80-R13 (checklist inaccurate) | UPHELD minor | Real doc gap: developer would get wrong instructions |
| 21-V01 (class name) | REFUTED_INTENTIONAL | Consistent naming convention; spec was illustrative |
