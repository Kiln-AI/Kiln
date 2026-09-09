# Cluster G — Runner Internal Design Deviations: Skeptic Verification

## 45-R02 / 45-R03 / 45-R12 / 15-R39: EvalJob.stored_output / stored_trace fields omitted

- **Skeptic verdict:** REFUTED_DEFERRED
- **Corrected verdict:** DEFERRED_OK
- **Corrected severity:** trivial
- **Reasoning:** The spec (Section 1, Section 3.3 of component 45) prescribes `stored_output` and `stored_trace` fields on EvalJob as a side-channel for carrying TaskRun output/trace data to V2 adapters in `eval_config_eval` mode. The code instead reads `job.item.output.output` and `job.item.trace` directly from the TaskRun at eval time (eval_runner.py:515-518), since `job.item` IS the TaskRun in that path. The spec's design is illustrative pseudocode (architecture spec, not a contract spec); the code achieves identical data flow with fewer indirections. No data is lost, no behavior diverges. The outcome — V2 adapters receive the same output/trace values via `EvalTaskInput.from_task_run(job.item)` — is identical.
- **Evidence:**
  - Spec: component 45 Section 1 (`stored_output: str | None = None -- NEW`) and Section 3.3 (collector injection pseudocode)
  - Code: `eval_runner.py:38-43` (EvalJob dataclass, no stored_output/stored_trace fields); `eval_runner.py:515` (`EvalTaskInput.from_task_run(job.item)` reads `.output.output` directly); `eval.py:332-347` (`EvalTaskInput.from_task_run` maps TaskRun fields directly)
  - Functional equivalence: Both paths produce identical `EvalTaskInput` with `final_message=task_run.output.output`, `trace=task_run.trace`

---

## 45-R21: B2.1 synthesizes EvalTaskInput directly, not intermediate EvalInput

- **Skeptic verdict:** REFUTED_DEFERRED
- **Corrected verdict:** DEFERRED_OK
- **Corrected severity:** trivial
- **Reasoning:** The spec (Section 5.2) describes synthesizing an in-memory `EvalInput` object from each TaskRun, which would then be consumed by V2 adapters. The code skips the intermediate `EvalInput` and builds `EvalTaskInput` directly from TaskRun via `EvalTaskInput.from_task_run()`. This is functionally equivalent because V2 adapters consume `EvalTaskInput` (not `EvalInput`) — the `EvalInput` would itself have been transformed into `EvalTaskInput` before adapter consumption. The spec even acknowledges this in Section 8.2: "V2 adapters always receive EvalInput (native or synthesized via B2.1)" but the actual adapter contract is `evaluate(EvalTaskInput)`. The extra intermediate object adds no value.
- **Evidence:**
  - Spec: Section 5.2 `_translate_task_run_to_eval_input(task_run) -> EvalInput`
  - Code: `eval_runner.py:488` (`EvalTaskInput.from_task_run(run_output)`), `eval_runner.py:515` (`EvalTaskInput.from_task_run(job.item)`)
  - `eval.py:332-347`: `EvalTaskInput.from_task_run` correctly maps all four fields (task_input, final_message, trace, reference_data)
  - Translation mapping from spec Section 5.2 table is fully honored: `TaskRun.input` -> `task_input`, `TaskRun.output.output` -> `final_message`, `TaskRun.trace` -> `trace`

---

## 45-R25: BaseEval.run_eval signature not widened; V2 routes via evaluate(EvalTaskInput)

- **Skeptic verdict:** REFUTED_DEFERRED
- **Corrected verdict:** DEFERRED_OK
- **Corrected severity:** trivial
- **Reasoning:** The spec (Section 5.3) widens `BaseEval.run_eval` to accept `TaskRun | EvalInput` + `stored_output`/`stored_trace`. The code instead keeps `run_eval` as the legacy-only path (`run_eval(self, task_run: TaskRun, eval_job_item: TaskRun | None = None)` at base_eval.py:124-126) and routes all V2 configs through `BaseV2EvalBridge.evaluate(EvalTaskInput)`. The spec itself notes this is "a mechanical consequence of B2.1, not a new design decision" and that "each concrete subclass narrows in practice; the union is a formality." The implementation achieves cleaner separation: legacy adapters never see V2 types, V2 adapters never use the legacy `run_eval` path. This is a superior design that avoids polluting the legacy interface.
- **Evidence:**
  - Spec: Section 5.3 (signature widening described as "mechanical" and "a formality")
  - Code: `base_eval.py:123-126` (legacy `run_eval` signature unchanged); `eval_runner.py:290-292` (V2 dispatches to `_run_v2_job` which calls `evaluator.evaluate(eval_task_input)` at lines 463, 489, 520)
  - V2 adapter contract: all V2 adapters implement `evaluate(EvalTaskInput) -> tuple[EvalScores, SkippedReason | None, str | None]` (verified in exact_match, contains, set_check, llm_judge, code_eval, tool_call_check, step_count_check)

---

## 45-R28 / 45-R42: Centralized _check_skip_conditions / _check_extraction not implemented; checks delegated to adapters / inline

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL
- **Corrected severity:** trivial
- **Reasoning:** The spec (Sections 5.1, 6.1, 6.2) describes centralized `_check_skip_conditions` and `_check_extraction` methods in the runner, called before adapter invocation. The code delegates these checks: `type_not_available` and `incompatible_input_shape` are inline in `_run_v2_job` (runner-level, just not in separate methods); `missing_reference_key`, `extraction_failed`, `missing_trace`, and `code_eval_not_trusted` are handled within individual adapters' `evaluate()` methods. All six SkippedReason values are correctly emitted and persisted. No skip condition is dropped. The only semantic difference is that `llm_judge` accessing `reference_data.*` via `required_var` produces `extraction_failed` rather than `missing_reference_key`, which is actually more precise since llm_judge doesn't declare a `reference_key` property — it uses expression-based extraction. The types that DO have `reference_key` properties (exact_match, contains, set_check) all correctly emit `missing_reference_key` via `check_reference_key()`. This is an architectural style difference (centralized vs delegated), not a behavioral gap.
- **Evidence:**
  - Runner-level checks: `eval_runner.py:393-412` (type_not_available via NotImplementedError catch); `eval_runner.py:414-439` (incompatible_input_shape inline); `eval_runner.py:441-459` (eval_config_eval + EvalInput deferred)
  - Adapter-level checks: `v2_eval_exact_match.py:28-33` (check_reference_key); `v2_eval_contains.py:28-34` (check_reference_key); `v2_eval_set_check.py:41-47` (check_reference_key); `v2_eval_llm_judge.py:105-107` (check_required_vars → extraction_failed); `v2_eval_code_eval.py:61-66` (code_eval_not_trusted); `v2_eval_tool_call_check.py:26-27` (missing_trace); `v2_eval_step_count_check.py:28-33` (missing_trace)
  - Skip helper: `v2_eval_helpers.py:48-75` (check_reference_key emits missing_reference_key for all 3 cases: no reference_data, missing key, key is None)
  - All persisted correctly: adapter returns `(scores={}, SkippedReason, detail)` → runner persists at `eval_runner.py:480-481, 509-510, 537-538`
  - No condition dropped: all 6 SkippedReason values from spec Section 6.3 table are emitted by code (verified per type)
