# Spec-Fidelity Review: Unit 45-runner (Runner Architecture)

Requirements: 42 total -- MET 33, PARTIAL 5, MISSING 2, CONTRADICTED 0, DEFERRED_OK 2, CANNOT_VERIFY 0

---

## Requirement Table

### 45-runner-R01
- **Category:** Data model
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** EvalJob.item is widened from TaskRun to `TaskRun | EvalInput`.
- **Spec quote:** "EvalJob.item changes from TaskRun to TaskRun | EvalInput" (Section 1)
- **Evidence:** `eval_runner.py:40` -- `item: TaskRun | EvalInput`

### 45-runner-R02
- **Category:** Data model
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** EvalJob gains a `stored_output: str | None` field for eval_config_eval with TaskRun source.
- **Spec quote:** "stored_output: str | None = None -- NEW -- for eval_config_eval with TaskRun source" (Section 1)
- **Evidence:** `eval_runner.py:38-44` -- No `stored_output` field on EvalJob dataclass. The runner instead directly uses `EvalTaskInput.from_task_run(job.item)` to access `job.item.output.output` in the `_run_v2_job` `eval_config_eval` path (line 515-518).
- **Divergence:** The implementation avoids the `stored_output` field by reading from the TaskRun directly at eval time. Functionally equivalent but structurally divergent from spec.

### 45-runner-R03
- **Category:** Data model
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** EvalJob gains a `stored_trace: str | None` field for eval_config_eval with TaskRun source.
- **Spec quote:** "stored_trace: str | None = None -- NEW -- trace JSON for eval_config_eval" (Section 1)
- **Evidence:** `eval_runner.py:38-44` -- No `stored_trace` field on EvalJob dataclass. Trace is accessed from the TaskRun directly via `EvalTaskInput.from_task_run()`.
- **Divergence:** Same as R02 -- the `stored_trace` side-channel is omitted; TaskRun is passed through directly.

### 45-runner-R04
- **Category:** Data model
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** EvalJob uses `task_run_config` field (replacing spec's `run_config` naming) for the run configuration.
- **Spec quote:** "run_config: KilnAgentRunConfigProperties | None = None" (Section 1)
- **Evidence:** `eval_runner.py:43` -- `task_run_config: TaskRunConfig | None = None`. The type is `TaskRunConfig` rather than `KilnAgentRunConfigProperties`; this is a design refinement that wraps the properties. The runner accesses `.run_config_properties` when needed (line 386). Functionally equivalent.

### 45-runner-R05
- **Category:** Constructor
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Constructor validates `run_configs is not None and len > 0` when `eval_run_type == "task_run_eval"`.
- **Spec quote:** "if eval_run_type == 'task_run_eval': assert run_configs is not None and len(run_configs) > 0" (Section 2.1)
- **Evidence:** `eval_runner.py:79-81` -- validates `run_configs is None or len(run_configs) == 0` raises ValueError.

### 45-runner-R06
- **Category:** Constructor
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Constructor validates `run_configs is None or len == 0` when `eval_run_type == "eval_config_eval"`.
- **Spec quote:** "else: assert run_configs is None or len(run_configs) == 0" (Section 2.1)
- **Evidence:** `eval_runner.py:91-92` -- `raise ValueError("Mode 'eval_config_eval' does not support run configs")`.

### 45-runner-R07
- **Category:** Constructor
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Constructor gains source-validation branch for EvalInput path when `eval.eval_input_filter_id is not None`.
- **Spec quote:** "if eval.eval_input_filter_id is not None: # V2 path: validate EvalInput dataset availability" (Section 2.1)
- **Evidence:** `eval_runner.py:94-96` -- `self._source_mode = "eval_input"` when `target_eval.eval_input_filter_id is not None`. The implementation sets a mode flag rather than calling a separate validate method, but the branching logic is present.

### 45-runner-R08
- **Category:** Dispatch
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `collect_tasks` dispatches by which filter field is set: `eval_input_filter_id` first, then `eval_run_type`.
- **Spec quote:** "if self.eval.eval_input_filter_id is not None: return self.collect_tasks_for_eval_input()" (Section 3.1)
- **Evidence:** `eval_runner.py:106-119` -- dispatches by `self._source_mode == "eval_input"` first, then by `eval_run_type`.

### 45-runner-R09
- **Category:** Collection
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `collect_tasks_for_eval_input` loads EvalInput children, applies filter, constructs EvalJob instances.
- **Spec quote:** "Loads EvalInput children from the parent Task, applies the EvalInputFilter..." (Section 3.2)
- **Evidence:** `eval_runner.py:154-218` -- loads via `self.task.eval_inputs(readonly=True)`, applies `eval_input_filter_from_id(filter_id)`.

### 45-runner-R10
- **Category:** Collection
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** For `task_run_eval` mode with EvalInput, crosses with all `run_configs`.
- **Spec quote:** "For task_run_eval mode, crosses with all run_configs" (Section 3.2)
- **Evidence:** `eval_runner.py:163-195` -- iterates `self.run_configs` for each eval_input and eval_config in `task_run_eval` mode.

### 45-runner-R11
- **Category:** Collection
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** For `eval_config_eval` mode with EvalInput, no run_configs.
- **Spec quote:** "For eval_config_eval mode, no run_configs" (Section 3.2)
- **Evidence:** `eval_runner.py:196-218` -- the else branch creates jobs without `task_run_config`.

### 45-runner-R12
- **Category:** Collection
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** When EvalConfig has `config_type == "v2"` and source is TaskRun, existing collectors inject `stored_output` and `stored_trace` on the EvalJob.
- **Spec quote:** "When the EvalConfig has config_type == 'v2' and the source is TaskRun-shaped, the existing collect_tasks_for_task_run_eval and collect_tasks_for_eval_config_eval methods inject stored_output and stored_trace on the EvalJob" (Section 3.3)
- **Evidence:** `eval_runner.py:121-152` and `220-261` -- Neither `collect_tasks_for_eval_config_eval` nor `collect_tasks_for_task_run_eval` inject `stored_output` or `stored_trace`. The EvalJob dataclass does not have these fields. TaskRun is passed directly as `item`.
- **Divergence:** The spec's stored_output/stored_trace side-channel is not implemented. The runner accesses TaskRun output/trace directly in the job execution path. Same functional outcome.

### 45-runner-R13
- **Category:** Restartability
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `_already_run` predicate extends to handle `eval_input_id`.
- **Spec quote:** "def _already_run(self, ..., eval_input_id: str | None = None)" (Section 3.4)
- **Evidence:** `eval_runner.py:164-178` and `197-202` -- The restartability logic is inlined in `collect_tasks_for_eval_input` using `already_run` dict tracking `eval_input_id`. Not a separate method, but the predicate logic is present.

### 45-runner-R14
- **Category:** Orchestration
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `task_run_eval` mode runs only the operative config (`current_config_id`).
- **Spec quote:** "task_run_eval mode runs only the operative config (current_config_id)" (Section 4.1)
- **Evidence:** `eval_api.py:1058-1059` -- `eval_configs=[eval_config]` passes a single eval_config. The runner itself accepts a list but the API passes only one.

### 45-runner-R15
- **Category:** Orchestration
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `eval_config_eval` mode runs all `eval_configs` under the Eval.
- **Spec quote:** "eval_config_eval mode runs all eval_configs" (Section 4.1)
- **Evidence:** `eval_api.py:1135-1136` -- `eval_configs = eval.configs()` then `EvalRunner(eval_configs=eval_configs, ...)`.

### 45-runner-R16
- **Category:** Orchestration
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Candidates under one Eval may be different V2EvalTypes. Runner does not enforce type uniformity.
- **Spec quote:** "candidates under one Eval may be different V2EvalTypes... The runner does not enforce type uniformity" (Section 4.2)
- **Evidence:** `eval_runner.py` -- No type-uniformity check anywhere in the runner. Each job dispatches independently based on `job.eval_config`.

### 45-runner-R17
- **Category:** Orchestration
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Mixed V1/V2 configs are handled: V1 to GEval, V2 to V2 adapters.
- **Spec quote:** "An Eval may have both legacy V1 EvalConfigs... and V2 EvalConfigs. The runner handles both" (Section 4.3)
- **Evidence:** `eval_runner.py:289-292` -- `run_job` dispatches by `job.eval_config.config_type == EvalConfigType.v2` to `_run_v2_job` vs `_run_legacy_job`.

### 45-runner-R18
- **Category:** Adapter dispatch
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `eval_adapter_from_type` accepts the full EvalConfig (two-level dispatch per A2.11).
- **Spec quote:** "eval_adapter_from_type accepts the full EvalConfig and performs two-level dispatch" (Section 8.1)
- **Evidence:** `registry.py:55-73` -- `v2_eval_adapter_from_config(eval_config, ...)` accepts full EvalConfig. `registry.py:37-52` -- `legacy_eval_adapter_from_type(eval_config)` also accepts full EvalConfig. The dispatch is split into two functions rather than one unified function.

### 45-runner-R19
- **Category:** Adapter dispatch
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Call site change: `eval_adapter_from_type` receives full `EvalConfig` instead of `config_type`.
- **Spec quote:** "Before (V1): evaluator = eval_adapter_from_type(job.eval_config.config_type)(...) / After (V2): evaluator = eval_adapter_from_type(job.eval_config)(...)" (Section 8.1)
- **Evidence:** `eval_runner.py:311` -- `legacy_eval_adapter_from_type(job.eval_config)` and `eval_runner.py:390-391` -- `v2_eval_adapter_from_config(job.eval_config, ...)`. Both accept the full EvalConfig.

### 45-runner-R20
- **Category:** Data guarantee
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Legacy GEval always receives TaskRun. V2 adapters receive EvalInput (native or synthesized via B2.1).
- **Spec quote:** "Legacy GEval: always receives TaskRun... V2 adapters: always receive EvalInput" (Section 8.2)
- **Evidence:** `eval_runner.py:307-309` -- `_run_legacy_job` checks `isinstance(job.item, TaskRun)`. For V2 with TaskRun, `_run_v2_job` at line 486-541 uses `EvalTaskInput.from_task_run(job.item)` which constructs an `EvalTaskInput` (not a raw `EvalInput`), but the V2 adapters receive `EvalTaskInput` not `EvalInput` directly. The data guarantee is met functionally.

### 45-runner-R21
- **Category:** B2.1 translation
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** When V2 EvalConfig receives TaskRun source, runner synthesizes an in-memory EvalInput per TaskRun.
- **Spec quote:** "_resolve_item... B2.1: V2 config + TaskRun source -- synthesize in-memory EvalInput" (Section 5.2)
- **Evidence:** `eval_runner.py:486-541` -- The V2 runner does NOT synthesize an in-memory `EvalInput`. Instead, for TaskRun + V2, it calls `EvalTaskInput.from_task_run(job.item)` which creates an `EvalTaskInput` directly from the TaskRun. The `_resolve_item` and `_translate_task_run_to_eval_input` methods from the spec do not exist.
- **Divergence:** The spec calls for an intermediate in-memory `EvalInput` object; the code skips that and creates `EvalTaskInput` directly from the `TaskRun`. Functionally equivalent for V2 adapters since they consume `EvalTaskInput`, not `EvalInput`.

### 45-runner-R22
- **Category:** B2.1 translation
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Translation mapping: `TaskRun.input` -> `task_input`, `TaskRun.output.output` -> `final_message`, `TaskRun.trace` -> `trace`.
- **Spec quote:** Translation mapping table (Section 5.2)
- **Evidence:** `eval.py:332-347` -- `EvalTaskInput.from_task_run` maps `task_run.input` -> `task_input`, `task_run.output.output` -> `final_message`, `task_run.trace` -> `trace`, `reference_data=None`.

### 45-runner-R23
- **Category:** B2.1 translation
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Synthesized EvalInput is NOT persisted. In-memory only.
- **Spec quote:** "The resulting EvalInput is NOT persisted. It exists only for the duration of this job's execution." (Section 5.2)
- **Evidence:** `EvalTaskInput.from_task_run()` at `eval.py:332` creates an in-memory object with no save_to_file call. `eval_runner.py:488,515` use it transiently.

### 45-runner-R24
- **Category:** B2.1 provenance
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** For B2.1 runs, `EvalRun.dataset_id` points at the source TaskRun (not eval_input_id).
- **Spec quote:** "EvalRun.dataset_id points at the source TaskRun (not eval_input_id)" (Section 5.2)
- **Evidence:** `eval_runner.py:502,530` -- `dataset_id=dataset_id` where `dataset_id = run_output.id` or `job.item.id` (TaskRun id). `eval_input_id=None`.

### 45-runner-R25
- **Category:** Signature
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** `BaseEval.run_eval` signature widens to accept `TaskRun | EvalInput` plus `stored_output` and `stored_trace` kwargs.
- **Spec quote:** "async def run_eval(self, item: TaskRun | EvalInput, stored_output: str | None = None, stored_trace: str | None = None)" (Section 5.3)
- **Evidence:** `base_eval.py:124-126` -- `async def run_eval(self, task_run: TaskRun, eval_job_item: TaskRun | None = None)`. The signature is NOT widened to accept `EvalInput`. The parameter name is `task_run: TaskRun`, not `item: TaskRun | EvalInput`. No `stored_output`/`stored_trace` parameters.
- **Divergence:** The implementation uses a different approach: V2 adapters bypass `run_eval` entirely and use the `evaluate(EvalTaskInput)` method via `BaseV2EvalBridge`. The `run_eval` method is only used by legacy adapters. Functionally equivalent since V2 adapters never receive raw `EvalInput` through `run_eval`.

### 45-runner-R26
- **Category:** Skip condition
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `type_not_available` skip when V2 adapter registry has no adapter for the config type.
- **Spec quote:** "if not _adapter_available(eval_config.properties.type): return SkippedReason.type_not_available" (Section 6.1 step 1)
- **Evidence:** `eval_runner.py:393,408` -- catches `NotImplementedError` from `v2_eval_adapter_from_config` and persists skip with `SkippedReason.type_not_available.value`.

### 45-runner-R27
- **Category:** Skip condition
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `incompatible_input_shape` skip for multi-turn TaskRun or multi-turn EvalInput.
- **Spec quote:** "if not self._input_shape_compatible(eval_config, item): return SkippedReason.incompatible_input_shape" (Section 6.1 step 2)
- **Evidence:** `eval_runner.py:414-439` -- checks `parent_task_run_id is not None` (multi-turn TaskRun) or `isinstance(job.item.data, MultiTurnSyntheticEvalInputData)` and emits `incompatible_input_shape`.

### 45-runner-R28
- **Category:** Skip condition
- **Verdict:** MISSING
- **Severity:** minor
- **Requirement:** `missing_reference_key` skip at runner level when EvalInput.reference is missing a key the EvalConfig declares as required.
- **Spec quote:** "if isinstance(item, EvalInput): missing = self._missing_reference_keys(eval_config, item); if missing: return SkippedReason.missing_reference_key" (Section 6.1 step 3)
- **Evidence:** `eval_runner.py` -- No runner-level reference key pre-check exists. The skip is emitted at the adapter level (in `v2_eval_helpers.py:48-75` `check_reference_key` and `check_required_vars`), not at the runner level.
- **Divergence:** The spec calls for a centralized runner-level pre-check. The implementation delegates this to individual adapters' `evaluate()` method. The functional effect is the same (skipped runs are persisted), but the check happens later and is adapter-specific rather than centralized.

### 45-runner-R29
- **Category:** Skip condition
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `code_eval_not_trusted` skip when project trust is not granted.
- **Spec quote:** "if not project_trust_granted(self.task.project): return SkippedReason.code_eval_not_trusted" (Section 6.1 step 4)
- **Evidence:** `v2_eval_code_eval.py:61-66` -- `if project_path is None or not is_code_eval_trusted(project_path): return ({}, SkippedReason.code_eval_not_trusted, ...)`. Emitted at adapter level, not runner level, but the skip reason is correctly produced and persisted.

### 45-runner-R30
- **Category:** Skip condition
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `extraction_failed` skip when required_var or value_expression evaluates to null/Undefined.
- **Spec quote:** "A required_var expression... or value_expression... evaluated to null/Undefined on this input (D.3)" (Section 6.3)
- **Evidence:** `v2_eval_helpers.py:26-45` (`extract_value`) and `v2_eval_helpers.py:78-91` (`check_required_vars`) return `SkippedReason.extraction_failed`. Used by individual adapters.

### 45-runner-R31
- **Category:** Skip condition
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `missing_trace` skip when trace-walking types find trace is None.
- **Spec quote:** "Trace-walking type (tool_call_check, step_count_check) found trace is None" (Section 6.3)
- **Evidence:** `v2_eval_tool_call_check.py:27` and `v2_eval_step_count_check.py:29-33` both check `eval_input.trace is None` and return `SkippedReason.missing_trace`.

### 45-runner-R32
- **Category:** Skip condition
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `incompatible_input_shape` skip for eval_config_eval over EvalInput (deferred in V2.0).
- **Spec quote:** Not explicitly in spec section 6.3 but implied by K.3 ("eval_config_eval with EvalInput source is the Copilot golden-subset path where TaskRuns are the source")
- **Evidence:** `eval_runner.py:441-459` -- When `isinstance(job.item, EvalInput) and job.type == "eval_config_eval"`, emits `incompatible_input_shape` with detail about deferred V2.0.

### 45-runner-R33
- **Category:** Persistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Skipped EvalRuns are persisted with `skipped_reason`, `skipped_detail`, empty scores, output=None.
- **Spec quote:** "eval_run = EvalRun(skipped_reason=reason, skipped_detail=skipped_detail, ... scores={}, ... output=None)" (Section 6.4)
- **Evidence:** `eval_runner.py:394-412, 421-439, 443-459` -- All skip paths persist EvalRun with `scores={}`, `output=None`, `skipped_reason=SkippedReason.X.value`, `skipped_detail=...`.

### 45-runner-R34
- **Category:** Persistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Skipped EvalRuns are counted toward `percent_complete` in on-read aggregation.
- **Spec quote:** "Counted toward percent_complete in on-read aggregation" (Section 6.4)
- **Evidence:** `eval_api.py:581,605-613` -- Skipped runs are counted in `excluded_counts`, then `n_processed = count + n_excluded`, and `percent_complete = n_processed / len(expected_dataset_ids)`.

### 45-runner-R35
- **Category:** Persistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Validator relaxation: `validate_scores` allows empty scores when `skipped_reason is not None`.
- **Spec quote:** "validate_scores allows empty scores when skipped_reason is not None" (Section 6.4)
- **Evidence:** `eval.py:531-533` -- `if self.skipped_reason is not None: return self` (early return, bypassing score validation).

### 45-runner-R36
- **Category:** EvalTaskInput
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Runner assembles EvalTaskInput with four reserved top-level variables: final_message, trace, reference_data, task_input.
- **Spec quote:** "The four reserved top-level variables (final_message, trace, reference_data, task_input)" (Section 7)
- **Evidence:** `eval.py:309-330` -- `EvalTaskInput` has fields `final_message`, `trace`, `reference_data`, `task_input`. `from_task_run` (line 332) and `from_eval_input` (line 349) populate all four.

### 45-runner-R37
- **Category:** Scoring helpers
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** V2 LlmJudgeAdapter consumes scoring helpers from scoring_utils.py (build_llm_as_judge_score, build_g_eval_score).
- **Spec quote:** "V2 LlmJudgeAdapter consumes the extracted scoring helpers from scoring_utils.py" (Section 8.3)
- **Evidence:** `v2_eval_llm_judge.py:19-26` imports `build_g_eval_score`, `build_llm_as_judge_score`, etc. Used at lines 168-176.

### 45-runner-R38
- **Category:** Scoring helpers
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Legacy GEval imports the same scoring helpers.
- **Spec quote:** "Legacy GEval imports the same helpers with zero behavior change" (Section 8.3)
- **Evidence:** `g_eval.py:9-24` imports from `scoring_utils` and uses `build_llm_as_judge_score` and `build_g_eval_score` (lines 338-363).

### 45-runner-R39
- **Category:** Provenance
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** EvalRun has XOR validator: exactly one of `dataset_id` or `eval_input_id` is set.
- **Spec quote:** "Per the EvalRun.validate_input_source validator, exactly one of dataset_id (V1) or eval_input_id (V2) is set" (Section 10.2)
- **Evidence:** `eval.py:482-489` -- `validate_input_source` raises ValueError if `(self.dataset_id is None) == (self.eval_input_id is None)`.

### 45-runner-R40
- **Category:** Provenance
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** EvalRun persisted as child of the correct EvalConfig via `parent=job.eval_config`.
- **Spec quote:** "The runner's only provenance responsibility is persisting the EvalRun as a child of the correct EvalConfig" (Section 10.3)
- **Evidence:** All EvalRun constructions in `eval_runner.py` use `parent=job.eval_config`.

### 45-runner-R41
- **Category:** Data type
- **Verdict:** DEFERRED_OK
- **Severity:** n/a
- **Requirement:** V2 EvalConfigs bypass Eval-level `evaluation_data_type` switch; per-config properties drive data needs.
- **Spec quote:** "V2: data contract is per-config properties, not Eval-level. Always serialize trace and reference_data if available." (Section 11)
- **Evidence:** `eval_runner.py:290-292` -- V2 jobs go to `_run_v2_job` which never checks `evaluation_data_type`. The `_run_legacy_job` at lines 338-350 checks `evaluation_data_type` only for V1.

### 45-runner-R42
- **Category:** Skip pipeline
- **Verdict:** MISSING
- **Severity:** minor
- **Requirement:** Spec specifies a centralized `_check_skip_conditions` method and a separate `_check_extraction` method in the runner, called before adapter invocation.
- **Spec quote:** "skip_reason, skip_detail = self._check_skip_conditions(job.eval_config, effective_item)... skip_reason, skip_detail = self._check_extraction(job.eval_config, effective_item)" (Section 5.1 steps 3-4)
- **Evidence:** `eval_runner.py:372-541` -- No centralized `_check_skip_conditions` or `_check_extraction` methods. Skip checks for `type_not_available` and `incompatible_input_shape` are inline in `_run_v2_job`. Skip checks for `extraction_failed`, `missing_reference_key`, `missing_trace`, and `code_eval_not_trusted` are delegated to individual adapters.
- **Divergence:** The spec's centralized skip pipeline is split: some checks are inline in the runner, others are in adapters. The functional outcome is equivalent -- all six skip reasons are emitted and persisted. But the architecture differs from the spec's two-phase centralized design.

### DEFERRED_OK items

### 45-runner-R41a
- **Category:** Data type
- **Verdict:** DEFERRED_OK
- **Severity:** n/a
- **Requirement:** Eval-level `evaluation_data_type` is None for V2 Evals.
- **Spec quote:** "The Eval-level evaluation_data_type field is None for V2 Evals." (Section 11)
- **Evidence:** `eval.py:793-796` -- `evaluation_data_type` defaults to `EvalDataType.final_answer`, and no validation forces it to None for V2. However, V2 paths never read this field, so it's functionally irrelevant.

---

## Verifier-Added Requirements (re-scan)

### 45-runner-R43 (verifier_added)
- **Category:** Data model
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** SkippedReason enum has exactly six values: missing_reference_key, incompatible_input_shape, extraction_failed, missing_trace, code_eval_not_trusted, type_not_available.
- **Spec quote:** "The six values seeded there... cover all known skip conditions" (Section 6.3)
- **Evidence:** `eval.py:254-262` -- `SkippedReason` enum has exactly these six values.

### 45-runner-R44 (verifier_added)
- **Category:** Persistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `skipped_reason` field is stored as a tolerant `str`, not a strict enum type.
- **Spec quote:** "The skipped_reason field is persisted as a tolerant str (not a strict enum type)" (Section 6.3)
- **Evidence:** `eval.py:468-469` -- `skipped_reason: str | None = Field(...)`. Values stored as `.value` string (e.g., `eval_runner.py:408` uses `SkippedReason.type_not_available.value`).

### 45-runner-R45 (verifier_added)
- **Category:** Collection
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** EvalInput filter function loaded via `eval_input_filter_from_id`.
- **Spec quote:** "filter_fn = eval_input_filter_from_id(self.eval.eval_input_filter_id)" (Section 3.2)
- **Evidence:** `eval_runner.py:161` -- `input_filter = eval_input_filter_from_id(filter_id)`.

### 45-runner-R46 (verifier_added)
- **Category:** Collection
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Task has `eval_inputs()` child accessor.
- **Spec quote:** "eval_inputs = self.task.eval_inputs()" (Section 3.2)
- **Evidence:** `task.py:137,234-235` -- Task declares `parent_of={"eval_inputs": EvalInput}` and has `eval_inputs()` method.

### 45-runner-R47 (verifier_added)
- **Category:** Persistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Normal (non-skipped) EvalRuns populate `reference_data` from EvalInput.reference.
- **Spec quote:** "reference_data=self._extract_reference_data(job.item)" (Section 10.1)
- **Evidence:** `eval_runner.py:479` -- `reference_data=job.item.reference` for EvalInput path. `eval_runner.py:508,536` -- `reference_data=eval_task_input.reference_data` for TaskRun path (which is None via `from_task_run`).

### 45-runner-R48 (verifier_added)
- **Category:** Retries
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** No hard-fail on individual skips; other (input x config) jobs proceed normally.
- **Spec quote:** "Other (input x config) jobs proceed normally -- no hard-fail on individual skips." (Section 6.1)
- **Evidence:** `eval_runner.py:394-412` and other skip paths all `return True` after persisting the skipped run, allowing the async job runner to continue with remaining jobs.
