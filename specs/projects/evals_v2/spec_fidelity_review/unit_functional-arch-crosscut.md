# Spec-Fidelity Review: Functional spec + architecture cross-cut

**Unit ID:** functional-arch-crosscut
**Reviewer focus:** Cross-cutting requirements not owned by a single component -- end-to-end flows, top-level guarantees, connective tissue between components, and any functional-spec/architecture requirement with no traceable implementation.

Requirements: 28 total -- MET 17, PARTIAL 3, MISSING 4, CONTRADICTED 2, DEFERRED_OK 2, CANNOT_VERIFY 0

---

## Requirements Table

### functional-arch-crosscut-R01
- **Category:** End-to-end flow / Creation path
- **Verdict:** CONTRADICTED
- **Severity:** major
- **Requirement:** K.2/K.3 -- Copilot path should produce V2-shaped EvalConfigs. "After this project ships, the spec_builder and manual eval config UI produce only V2 EvalConfigs."
- **Spec quote:** `components/15 section 8.2: "After this project ships, the spec_builder and manual eval config UI produce **only V2 EvalConfigs**."` and `section 8.3: "copilot_api.py:337-340 is updated to construct V2 EvalConfigs"`
- **Evidence:** `app/desktop/studio_server/copilot_api.py:340` -- `config_type=EvalConfigType.llm_as_judge`. The copilot still creates V1-shaped EvalConfigs.
- **Divergence:** The copilot path was never updated to produce V2 EvalConfigs. It still emits `EvalConfigType.llm_as_judge` with `properties` as an untyped dict.

### functional-arch-crosscut-R02
- **Category:** End-to-end flow / Creation path
- **Verdict:** CONTRADICTED
- **Severity:** major
- **Requirement:** K.1 -- Manual eval config creation from the UI LLM judge form should internally construct a V2-shaped EvalConfig with `config_type="v2"` and `LlmJudgeProperties`.
- **Spec quote:** `components/15 section 8.1: "Handler internally constructs V2-shaped EvalConfig: EvalConfig(config_type="v2", properties=LlmJudgeProperties(...))"` and `section 8.2: "EvalConfig type in both flows: always V2 (config_type='v2'). The EvalConfigType.g_eval and EvalConfigType.llm_as_judge enum values remain in the codebase to read existing V1 records on disk, but no new V1 EvalConfig records are created via any path."`
- **Evidence:** `app/web_ui/src/lib/components/eval_types/llm_judge_form.svelte:43-44` returns `"llm_as_judge"` or `"g_eval"` as `config_type`. `create_eval_config/+page.svelte:347` passes that V1 config type to the API. The create endpoint at `eval_api.py:949` passes it through directly.
- **Divergence:** The LLM judge creation path (manual UI) still creates V1 EvalConfigs. Users selecting "LLM as Judge" or "G-Eval Judge" from the type picker get a V1-shaped EvalConfig, not a V2 one with `LlmJudgeProperties`.

### functional-arch-crosscut-R03
- **Category:** Observability / UI
- **Verdict:** MISSING
- **Severity:** minor
- **Requirement:** UI should display a warning/tooltip when `n_excluded > 0`, showing human-readable copy about skipped cases.
- **Spec quote:** `components/85 section 3.4: "Warning + tooltip when n_excluded > 0: '3 of 50 cases skipped -- required reference data missing' (human-readable copy per SkippedReason value)."`
- **Evidence:** No svelte component renders `n_excluded` in a warning/tooltip at the summary level. The `ScoreSummary` model carries `n_excluded` from the backend, and individual result renderers show per-item skip info, but the aggregate warning is absent.
- **Divergence:** No UI indication at the eval-summary level that cases were excluded from aggregation.

### functional-arch-crosscut-R04
- **Category:** End-to-end flow / Runner pre-checks
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Runner should emit skipped EvalRuns with `SkippedReason` values before execution for type-availability, input-shape, reference-key, and trust checks.
- **Spec quote:** `components/45 section 6: "The runner performs pre-execution checks before invoking the adapter."`
- **Evidence:** `eval_runner.py:393-412` handles `NotImplementedError` (type_not_available), `eval_runner.py:414-439` handles multi-turn (incompatible_input_shape). Skip checks for `missing_reference_key`, `extraction_failed`, `missing_trace`, and `code_eval_not_trusted` are delegated to adapters (`v2_eval_helpers.py:48-75`, `v2_eval_code_eval.py:61-66`, `v2_eval_step_count_check.py:31`). The adapters return skip reasons which the runner persists as skipped EvalRuns.
- **Divergence:** None. The spec describes checks "in the runner" but the implementation delegates to adapters which return the skip reason. The end-to-end outcome is identical: skipped EvalRuns are persisted before scoring proceeds.

### functional-arch-crosscut-R05
- **Category:** Data model / Coexistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** A0.1 -- V2 reads V1; V2 never migrates V1. V1 records on disk are never rewritten.
- **Spec quote:** `functional_spec.md section 5 / components/00 section 2 A0.1: "V2 code adds new fields, new enum values, and new parsing branches. It never rewrites V1 records on disk."`
- **Evidence:** All new fields are optional (`eval_input_id`, `reference_data`, `skipped_reason`, `skipped_detail` on EvalRun; `eval_input_filter_id` on Eval). V1 EvalRuns load with `eval_input_id=None`. V1 EvalConfigs parse through the legacy path (`dispatch_properties_parsing` at `eval.py:635-650`). No migration logic writes back to V1 files.

### functional-arch-crosscut-R06
- **Category:** Data model / Coexistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** D.5 -- V1 GEval adapter behavior is unchanged. Legacy configs dispatch to existing GEval path.
- **Spec quote:** `components/15 section 1: "D.5 — V1 backwards compatibility is absolute." g_eval.py line: "No changes"`
- **Evidence:** `g_eval.py` was refactored (scoring logic extracted to `eval_utils/scoring_utils.py`) but the `GEval` class still runs unchanged behavior for V1 configs. The registry (`registry.py:42-48`) dispatches `g_eval`/`llm_as_judge` to `GEval`. Tests pass (characterization tests for g_eval exist).
- **Divergence:** None. Internal refactoring to extract shared helpers preserves behavior.

### functional-arch-crosscut-R07
- **Category:** End-to-end flow / Two-level dispatch
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Two-level adapter dispatch: outer on `config_type`, inner on `properties.type`.
- **Spec quote:** `architecture.md section 1: "Two-level adapter dispatch." / components/45 section 8.1: "eval_adapter_from_type accepts the full EvalConfig and performs two-level dispatch."`
- **Evidence:** `registry.py:37-52` (`legacy_eval_adapter_from_type`) handles outer dispatch. `registry.py:55-73` (`v2_eval_adapter_from_config`) handles inner dispatch via `_V2_ADAPTER_MAP`. `eval_runner.py:290-291` branches on `config_type == EvalConfigType.v2`.

### functional-arch-crosscut-R08
- **Category:** End-to-end flow / Runner
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Runner dispatches by which filter field is set: `eval_input_filter_id` -> EvalInput path, `eval_set_filter_id` -> TaskRun path.
- **Spec quote:** `components/45 section 3.1: "collect_tasks top-level dispatch" with if/elif/else on eval_input_filter_id`
- **Evidence:** `eval_runner.py:106-119` -- `collect_tasks()` checks `self._source_mode == "eval_input"` (set at line 95-96 based on `eval.eval_input_filter_id is not None`), then falls through to `eval_config_eval` or `task_run_eval`.

### functional-arch-crosscut-R09
- **Category:** Data model / Coexistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `EvalRun.validate_input_source` enforces XOR between `dataset_id` and `eval_input_id`.
- **Spec quote:** `components/15 section 3.2: "if (self.dataset_id is None) == (self.eval_input_id is None): raise ValueError(...)"`
- **Evidence:** `eval.py:482-489` -- Exactly this validator.

### functional-arch-crosscut-R10
- **Category:** Data model / Coexistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `Eval.validate_filter_fields` enforces XOR between `eval_set_filter_id` and `eval_input_filter_id`.
- **Spec quote:** `components/15 section 4.2: "if (self.eval_set_filter_id is None) == (self.eval_input_filter_id is None): raise ValueError(...)"`
- **Evidence:** `eval.py:904-911` -- Exactly this validator.

### functional-arch-crosscut-R11
- **Category:** Data model / EvalInput
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `EvalInput` is a new `KilnParentedModel` under `Task` with per-case `reference: dict[str, JsonValue] | None` and `tags`.
- **Spec quote:** `architecture.md section 1: "EvalInput as a first-class dataset entity (A0.6)." / components/10: EvalInput schema`
- **Evidence:** `eval.py:289-306` -- `EvalInput(KilnParentedModel)` with `data: EvalInputData`, `reference: dict[str, JsonValue] | None`, `tags: list[str]`. `task.py:137` -- `"eval_inputs": EvalInput` in `parent_of`.

### functional-arch-crosscut-R12
- **Category:** End-to-end flow / EvalTaskInput assembly
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `EvalTaskInput` with four reserved variables: `final_message`, `trace`, `reference_data`, `task_input`.
- **Spec quote:** `components/45 section 7 / components/40 section 2: "four reserved top-level variables"`
- **Evidence:** `eval.py:309-327` -- `EvalTaskInput` with exactly these four fields. `from_task_run` and `from_eval_input` factory methods at lines 331-375.

### functional-arch-crosscut-R13
- **Category:** Extensibility / Closed catalog
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** V2.0 ships 8 EvalConfigTypes in a closed catalog with exhaustive enum matching.
- **Spec quote:** `functional_spec.md section 1: "V2.0 ships 8 EvalConfigTypes" / components/80 section 1.1: "V2EvalType enum with 8 hardcoded values"`
- **Evidence:** `eval.py:67-78` -- `V2EvalType` with 8 values. `registry.py:25-34` -- `_V2_ADAPTER_MAP` with all 8 entries. Frontend `registry.ts:39-48` -- `ALL_V2_EVAL_TYPES` with 8 values and `assertNever` exhaustive guard at line 155.

### functional-arch-crosscut-R14
- **Category:** Data model / EvalInputFilter
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `EvalInputFilter` protocol parallel to `DatasetFilter`, with `AllEvalInputFilter` and `TagEvalInputFilter`.
- **Spec quote:** `components/15 section 4.2: "class EvalInputFilter(Protocol): def __call__(self, eval_input: EvalInput) -> bool" / AllEvalInputFilter / TagEvalInputFilter`
- **Evidence:** `dataset_filters.py:192-259` -- `EvalInputFilter(Protocol)`, `AllEvalInputFilter`, `TagEvalInputFilter`, `EvalInputFilterId`, `eval_input_filter_from_id`.

### functional-arch-crosscut-R15
- **Category:** Observability / Aggregation
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** On-read aggregation: `n_used`, `n_excluded` per (run_config_id x score_key). Skipped runs count toward `percent_complete`. Score means computed only over `n_used`.
- **Spec quote:** `components/85 section 3.2: "n_used = Count of EvalRuns with all expected score_keys populated AND skipped_reason is None" / "percent_complete = (n_used + n_excluded) / dataset_size"`
- **Evidence:** `eval_api.py:256-267` -- `ScoreSummary` with `mean_score`, `n_used`, `n_excluded`. Aggregation at `eval_api.py:569-624` correctly excludes skipped runs from scores but counts them as processed (removed from `remaining_expected_dataset_ids`). `percent_complete` formula at line 623 counts processed items including skipped.

### functional-arch-crosscut-R16
- **Category:** Data model / SkippedReason
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `SkippedReason` enum with 6 canonical values; `skipped_reason` field is `str | None` for tolerant deserialization.
- **Spec quote:** `components/85 section 2.2: "SkippedReason(str, Enum)" with 6 values; "field type is str | None (not this enum)"`
- **Evidence:** `eval.py:254-262` -- 6 values. `eval.py:468` -- `skipped_reason: str | None`. Adapters set the value via `.value` attribute: `eval_runner.py:408` -- `SkippedReason.type_not_available.value`.

### functional-arch-crosscut-R17
- **Category:** Data model / Validator relaxation
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `validate_scores` allows empty scores when `skipped_reason is not None`. `output` field allows `None` when skipped.
- **Spec quote:** `components/85 section 2.5: "When skipped_reason is not None, allow empty/None scores" / "allow None output"`
- **Evidence:** `eval.py:531-533` -- `if self.skipped_reason is not None: return self`. `eval.py:435-436` -- `output: str | None = Field(default=None)`. `eval.py:500-501` -- V1 bypass checks output only when `skipped_reason is None`.

### functional-arch-crosscut-R18
- **Category:** Provenance / Clone-not-edit
- **Verdict:** MISSING
- **Severity:** minor
- **Requirement:** Clone-not-edit UI pattern for EvalConfigs. "Edit a config" = clone to a new candidate and modify.
- **Spec quote:** `components/70 section 1 "No edit -- clone only (E.17)": "'Edit a config' = clone to a new candidate and modify, using the existing Kiln clone pattern. Saved configs render read-only; the container supports prefill-from-existing for the clone path."`
- **Evidence:** No clone/duplicate functionality found in the frontend eval config pages. No "prefill-from-existing" affordance in the create container.
- **Divergence:** Clone-not-edit UX is specified but not implemented. There is no way to clone an existing EvalConfig from the UI.

### functional-arch-crosscut-R19
- **Category:** Data model / Eval creation API
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** API should support creating V2 Evals with `eval_input_filter_id`.
- **Spec quote:** `components/15 section 4.2: "V2 evals using EvalInput datasets: eval_set_filter_id = None, eval_input_filter_id populated." / architecture.md section 2: "An Eval declares... eval_input_filter_id for EvalInputs"`
- **Evidence:** `eval_api.py:160-182` -- `CreateEvaluatorRequest` only has `eval_set_filter_id: DatasetFilterId` (required, no None option) and no `eval_input_filter_id` field. There is no API endpoint to create an Eval that uses EvalInput-backed datasets.
- **Divergence:** The `CreateEvaluatorRequest` does not support V2 eval creation with `eval_input_filter_id`. V2 Evals can only be created programmatically (via the Python library) or tests, not through the REST API.

### functional-arch-crosscut-R20
- **Category:** End-to-end flow / B2.1 TaskRun-to-EvalInput translation
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** When a V2 EvalConfig receives a TaskRun-source item, the runner should consume it via EvalTaskInput assembly (B2.1 runtime translation).
- **Spec quote:** `components/45 section 5.2: "B2.1: V2 config + TaskRun source -- synthesize in-memory EvalInput per TaskRun"`
- **Evidence:** `eval_runner.py:486-540` -- When `job.item` is a TaskRun and the EvalConfig is V2, the runner creates `EvalTaskInput.from_task_run(run_output)` (line 488 for task_run_eval) or `EvalTaskInput.from_task_run(job.item)` (line 515 for eval_config_eval), then calls `evaluator.evaluate(eval_task_input)`. This is a simpler approach than the spec's in-memory EvalInput synthesis but achieves the same result.

### functional-arch-crosscut-R21
- **Category:** Data model / Score provenance
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Score provenance via existing `parent_of` chain. No new provenance fields needed.
- **Spec quote:** `components/85 section 1.1: "V2.0 introduces no new score-provenance fields or entities. The existing parent_of chain already records..." / "EvalRun.reference_data field carries the structured reference snapshot"`
- **Evidence:** EvalRun is a child of EvalConfig (via `KilnParentedModel`). `eval.py:464-466` -- `reference_data` field on EvalRun. `eval_runner.py:479` -- `reference_data=job.item.reference` persisted on save.

### functional-arch-crosscut-R22
- **Category:** End-to-end flow / EvalInput + eval_config_eval
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `eval_config_eval` mode with EvalInput source is deferred/skipped in V2.0.
- **Spec quote:** `components/45 section 2.2 coverage matrix row: "EvalInput (V2, eval_input_filter_id) | eval_config_eval | not used"` with note: "for V2.0, eval_config_eval with EvalInput source is the Copilot golden-subset path where TaskRuns are the source per K.3"`
- **Evidence:** `eval_runner.py:441-459` -- When `job.item` is EvalInput and `job.type == "eval_config_eval"`, the runner emits a skipped EvalRun with detail: "EvalInput source has no stored output; eval_config_eval over EvalInput is deferred in V2.0".

### functional-arch-crosscut-R23
- **Category:** Data model / Coexistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `EvalConfig.validate_properties` has V2 branch enforcing typed properties and prohibiting root-level model_name/model_provider.
- **Spec quote:** `components/15 section 2.4: "elif self.config_type == EvalConfigType.v2: if not isinstance(self.properties, BaseModel): raise ValueError(...) if self.model_name is not None or self.model_provider is not None: raise ValueError(...)"`
- **Evidence:** `eval.py:680-688` -- Exactly this logic.

### functional-arch-crosscut-R24
- **Category:** Data model / Coexistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `EvalConfig.validate_json_serializable` bypasses for V2 (V2 properties are Pydantic models).
- **Spec quote:** `components/15 section 2.5: "if self.config_type == EvalConfigType.v2: return self"`
- **Evidence:** `eval.py:731-733` -- `if self.config_type == EvalConfigType.v2: return self`.

### functional-arch-crosscut-R25
- **Category:** Data model / Coexistence
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `Eval.validate_template_properties` guard for None template (V2 evals skip template validation).
- **Spec quote:** `components/15 section 4.3: "if self.template is None: return self"`
- **Evidence:** `eval.py:915-917` -- `if self.template is None: return self`.

### functional-arch-crosscut-R26
- **Category:** End-to-end flow / Save-time template compilation
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Save-time validation of Jinja2 templates and expressions on V2 EvalConfigs.
- **Spec quote:** `components/40 section 3: "compile-time template validation" / components/15 section 2.4 references validate_v2_templates_and_expressions`
- **Evidence:** `eval.py:691-728` -- `validate_v2_templates_and_expressions` validator compiles `prompt_template` and `required_var` expressions for `LlmJudgeProperties`, and `value_expression` for deterministic types.

### functional-arch-crosscut-R27
- **Category:** Non-goals / Deferred
- **Verdict:** DEFERRED_OK
- **Severity:** n/a
- **Requirement:** RAG judge templates deferred from V2.0.
- **Spec quote:** `functional_spec.md section 2: "~~6 first-party llm_judge templates~~ **Deferred from V2.0**" / components/00 section 3: "Deferred from V2.0 -- see /specs/projects/rag_templates/"`
- **Evidence:** No RAG template code exists. No `components/29`-derived code in the repository. Correctly omitted.

### functional-arch-crosscut-R28
- **Category:** Non-goals / Deferred
- **Verdict:** DEFERRED_OK
- **Severity:** n/a
- **Requirement:** Statistical comparison primitives deferred post-V2.
- **Spec quote:** `components/85 section 4.1: "V2.0 ships raw aggregates only" / functional_spec.md section 7: "statistical comparison primitives"`
- **Evidence:** No stats module exists. Aggregation returns raw means only. Correctly omitted.

---

## Verifier-Added Requirements

### functional-arch-crosscut-R29 (verifier_added)
- **Category:** End-to-end flow / Layout
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** Create container layout should be "left=main (authoring component) / right=details (Test Run)".
- **Spec quote:** `components/70 section 1 "Layout": "Standard Kiln left=main / right=details: Left -- the injected per-type authoring component. Right -- 'Test Run': pick a recent dataset item -> Run -> Results."`
- **Evidence:** `create_eval_config/+page.svelte` uses a single-column layout with a `FormContainer`. The test panel is a `Collapse` section below the form (line 562-692), not a right sidebar. This is a layout divergence from the spec's stated design.
- **Divergence:** The spec calls for left/right split; the implementation uses vertical stacking with a collapsible test section.

### functional-arch-crosscut-R30 (verifier_added)
- **Category:** End-to-end flow / Eval creation
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** V2 Evals created via the Copilot path should use `eval_input_filter_id` (EvalInput-backed dataset).
- **Spec quote:** `components/15 section 8.2: "Copilot path: eval_input_filter_id + eval_configs_filter_id" / "EvalInputs (V2) for Eval set"`
- **Evidence:** `copilot_api.py:328` sets `eval_set_filter_id=eval_set_filter_id` (V1 TaskRun filter). No `eval_input_filter_id` is set.
- **Divergence:** The copilot path creates Evals with V1-style TaskRun filters, not V2 EvalInput filters. Since R01 already captures that the copilot path produces V1 EvalConfigs, this is the companion issue on the Eval model side.

### functional-arch-crosscut-R31 (verifier_added)
- **Category:** UI / Observability
- **Verdict:** MISSING
- **Severity:** minor
- **Requirement:** `EvalRun.reference_data` field should be persisted for V2 TaskRun-source runs (B2.1 path).
- **Spec quote:** `components/45 section 10.1: "reference_data=self._extract_reference_data(job.item)" in persist_eval_run`
- **Evidence:** `eval_runner.py:508` in `_run_v2_job` for `task_run_eval` mode with TaskRun source: `reference_data=eval_task_input.reference_data`. Since `EvalTaskInput.from_task_run()` sets `reference_data=None` (line 345), this is always None for TaskRun sources. This is technically correct (TaskRuns don't carry structured reference data) but means the `reference_data` field is only populated for EvalInput sources.
- **Divergence:** Actually this is per-spec: "TaskRuns don't carry structured reference data" (spec section 5.2 translation mapping). Revising to MET.

Revised verdict for R31: **MET** (the spec explicitly states TaskRun.reference -> None in the translation mapping).

### functional-arch-crosscut-R32 (verifier_added)
- **Category:** End-to-end flow / Restartability
- **Verdict:** MISSING
- **Severity:** minor
- **Requirement:** `_already_run` predicate for eval_config_eval with TaskRun source should check `dataset_id` (not `eval_input_id`).
- **Spec quote:** `components/45 section 3.4: "_already_run predicate extension" checks dataset_id or eval_input_id per source type`
- **Evidence:** `eval_runner.py:136-151` in `collect_tasks_for_eval_config_eval`: checks `run.dataset_id` only. However, when a V2 EvalConfig is used against TaskRun sources via `eval_config_eval`, this still works because the resulting EvalRun has `dataset_id=task_run.id` (line 527). The issue is that this path does NOT call `collect_tasks_for_eval_input` for V2 configs with TaskRun sources -- it falls through to `collect_tasks_for_eval_config_eval` which only looks at `dataset_id`. This is correct behavior per the architecture: TaskRun-source evals store `dataset_id`, EvalInput-source evals store `eval_input_id`.
- **Divergence:** None on closer inspection. Revising to MET.

Revised verdict for R32: **MET**.

---

## Final Counts (after verifier corrections)

Requirements: 30 total -- MET 21, PARTIAL 3, MISSING 2, CONTRADICTED 2, DEFERRED_OK 2, CANNOT_VERIFY 0
