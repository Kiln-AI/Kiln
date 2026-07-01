# Spec-Fidelity Review: Unit 20-types-overview — Eval config types overview / adapter contract

Requirements: 32 total — MET 24, PARTIAL 5, MISSING 0, CONTRADICTED 0, DEFERRED_OK 2, CANNOT_VERIFY 1

---

## Requirements Table

### 20-types-overview-R01
- **Category:** Enum definition
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** V2.0 ships exactly 8 EvalConfigTypes in the `V2EvalType` enum: `llm_judge`, `exact_match`, `pattern_match`, `set_check`, `contains`, `tool_call_check`, `step_count_check`, `code_eval`.
- **Spec quote:** Section 1, table rows 1-8
- **Evidence:** `libs/core/kiln_ai/datamodel/eval.py:67-78` — `V2EvalType(str, Enum)` with exactly these 8 members.

### 20-types-overview-R02
- **Category:** Data model
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Each type has a dedicated properties class (Pydantic BaseModel with a `type: Literal[...]` discriminator field).
- **Spec quote:** Section 1 para 1: "Each type has a dedicated properties class (Pydantic BaseModel with a `type: Literal[...]` discriminator field)"
- **Evidence:** `eval.py:81-224` — `LlmJudgeProperties`, `ExactMatchProperties`, `PatternMatchProperties`, `ContainsProperties`, `SetCheckProperties`, `ToolCallCheckProperties`, `StepCountCheckProperties`, `CodeEvalProperties`, all with `type: Literal[V2EvalType.xxx]`.

### 20-types-overview-R03
- **Category:** Data model
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `V2EvalConfigProperties` is an `Annotated[Union[...], Discriminator("type")]` discriminated union of all 8 properties classes.
- **Spec quote:** Section 1: "8 types in... `V2EvalConfigProperties` discriminated union"
- **Evidence:** `eval.py:226-238` — `V2EvalConfigProperties = Annotated[Union[LlmJudgeProperties, ExactMatchProperties, ...], Discriminator("type")]` with all 8 types.

### 20-types-overview-R04
- **Category:** Adapter registration
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Each type has a corresponding adapter (subclass of BaseEval) registered in `_V2_ADAPTER_MAP`.
- **Spec quote:** Section 1 para 1 + Section 2.2
- **Evidence:** `registry.py:25-34` — `_V2_ADAPTER_MAP` maps all 8 `V2EvalType` values to adapter classes. All adapters subclass `BaseV2EvalBridge` which subclasses `BaseEval`.

### 20-types-overview-R05
- **Category:** Dispatch architecture
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Two-level adapter dispatch: outer on `EvalConfig.config_type` (legacy vs `"v2"`), inner on `properties.type` (V2 discriminator).
- **Spec quote:** Section 2.1 dispatch flow diagram
- **Evidence:** `eval_runner.py:290-293` dispatches on `config_type == v2` to `_run_v2_job` vs `_run_legacy_job`. `registry.py:55-73` (`v2_eval_adapter_from_config`) reads `properties.type` and looks up `_V2_ADAPTER_MAP`.

### 20-types-overview-R06
- **Category:** Legacy path
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Legacy `g_eval`/`llm_as_judge` paths return `GEval` (unchanged, per D.5).
- **Spec quote:** Section 2.1: "config_type == 'g_eval' or 'llm_as_judge' -> LEGACY PATH: return GEval"
- **Evidence:** `registry.py:37-52` — `legacy_eval_adapter_from_type` returns `GEval` for both `g_eval` and `llm_as_judge`.

### 20-types-overview-R07
- **Category:** Registry signature
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** The registry entry point changes from taking the enum value to taking the full `EvalConfig`. Single combined function `eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]`.
- **Spec quote:** Section 2.2: `def eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]` followed by `_v2_adapter_from_properties_type`
- **Evidence:** `registry.py:37,55` — Two separate functions instead of one: `legacy_eval_adapter_from_type(eval_config) -> type[BaseEval]` and `v2_eval_adapter_from_config(eval_config, ...) -> BaseV2EvalBridge`. The dispatch is split across the caller (`eval_runner.py:290-293`) rather than unified in the registry.
- **Divergence:** The spec envisions a single unified entry point; the implementation splits into two functions with the caller doing the outer dispatch. Functionally equivalent but architecturally different from the spec's design. The V2 function also returns an **instance** rather than a **class** (`type[BaseEval]`), which is another signature change.

### 20-types-overview-R08
- **Category:** Registry map
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** `_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseEval]]` — map keyed on V2EvalType, valued as `type[BaseEval]`.
- **Spec quote:** Section 2.2: `_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseEval]] = {...}`
- **Evidence:** `registry.py:25` — `_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseV2EvalBridge]]`. Typed as `BaseV2EvalBridge` not `BaseEval`.
- **Divergence:** Map value type is `type[BaseV2EvalBridge]` instead of `type[BaseEval]`. This is narrower (subclass), so it works but introduces the `BaseV2EvalBridge` intermediate that the spec did not envision.

### 20-types-overview-R09
- **Category:** Dispatch error handling
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Unknown V2 type raises (exhaustive enum match).
- **Spec quote:** Section 2.1: "unknown type -> raise (exhaustive enum match)"
- **Evidence:** `registry.py:71-72` — raises `NotImplementedError` for unknown types. The runner at `eval_runner.py:393` catches `NotImplementedError` and writes a skipped run.

### 20-types-overview-R10
- **Category:** Discriminator mechanism
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Outer discriminator (`config_type`) is NOT a Pydantic discriminator — it's a plain field + model_validator. Values: `g_eval`, `llm_as_judge`, `v2`.
- **Spec quote:** Section 2.3: "Outer (config_type on EvalConfig): A plain field + model_validator..."
- **Evidence:** `eval.py:59-64` — `EvalConfigType` enum with `g_eval`, `llm_as_judge`, `v2`. The `EvalConfig` class at line 630 uses it as a field; model_validator handles parsing.

### 20-types-overview-R11
- **Category:** Discriminator mechanism
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Inner discriminator (`type` on V2 properties) uses standard Pydantic v2 `Annotated[Union[...], Discriminator("type")]`.
- **Spec quote:** Section 2.3: "Inner (type on each V2 properties variant): The standard Pydantic v2 Annotated[Union[...], Discriminator('type')] pattern."
- **Evidence:** `eval.py:226-238` — `V2EvalConfigProperties = Annotated[Union[...], Discriminator("type")]`.

### 20-types-overview-R12
- **Category:** Adapter base class
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** V2 adapters subclass the existing `BaseEval`. There is no `BaseEvalV2` class. No fork.
- **Spec quote:** Section 3.1: "V2 adapters subclass the existing BaseEval. There is no BaseEvalV2 class."
- **Evidence:** `base_eval.py:217-254` — There IS an intermediate class `BaseV2EvalBridge(BaseEval)` that all V2 adapters subclass. While it IS a subclass of `BaseEval` (so not a "fork" per se), it is an additional layer the spec explicitly said would not exist. The spec says "no BaseEvalV2 fork" and this is effectively a V2-specific bridge class.
- **Divergence:** `BaseV2EvalBridge` exists as a V2-specific intermediate base class with its own `evaluate()` abstract method and `run_eval()` bridge. The spec intended V2 adapters to directly subclass `BaseEval`. The bridge serves a legitimate purpose (translating `TaskRun` to `EvalTaskInput`) but was not designed in the spec.

### 20-types-overview-R13
- **Category:** Model field access
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** `BaseEval.model_and_provider()` is extracted into a separate helper module (e.g. `legacy_model_fields.py`). Legacy GEval calls the helper. V2 llm_judge reads from its own properties. V2 non-LLM types never touch model fields.
- **Spec quote:** Section 3.2: "extracted into a separate helper module (e.g. `kiln_ai/adapters/eval/legacy_model_fields.py`)"
- **Evidence:** `base_eval.py:24-44` — `model_and_provider_from_config()` is a standalone function in `base_eval.py`, not a separate module. `BaseEval.model_and_provider()` at line 73-74 delegates to it. GEval at `g_eval.py:261` calls `self.model_and_provider()`. LlmJudgeEval at `v2_eval_llm_judge.py:126-127` reads from `props.model_name`/`props.model_provider` directly.
- **Divergence:** The helper function exists but was NOT extracted to a separate module (`legacy_model_fields.py`). It remains in `base_eval.py` as a module-level function. The functional goal is achieved (decoupled access), but the organizational structure differs. `model_and_provider()` remains on `BaseEval` as a method.

### 20-types-overview-R14
- **Category:** Adapter contract
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Every V2 adapter subclasses BaseEval.
- **Spec quote:** Section 3.3 point 1
- **Evidence:** All 8 V2 adapters subclass `BaseV2EvalBridge` which subclasses `BaseEval`. Verified across all `v2_eval_*.py` files.

### 20-types-overview-R15
- **Category:** Adapter contract
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** V2 adapters receive either `TaskRun` or `EvalInput` via the runner.
- **Spec quote:** Section 3.3 point 2: "Receives either TaskRun or EvalInput via the runner"
- **Evidence:** `eval_runner.py:375-382` — `_run_v2_job` handles both `TaskRun` and `EvalInput` job items. `BaseV2EvalBridge.run_eval` at `base_eval.py:245-254` converts `TaskRun` to `EvalTaskInput` via `EvalTaskInput.from_task_run`.

### 20-types-overview-R16
- **Category:** Adapter contract
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** V2 adapters use `BaseEval.build_score_schema()` for score-schema generation.
- **Spec quote:** Section 3.3 point 3
- **Evidence:** `base_eval.py:69` — `self.score_schema = BaseEval.build_score_schema(eval, allow_float_scores=True)` in `BaseEval.__init__`. `v2_eval_llm_judge.py:114` calls `BaseEval.build_score_schema(self.eval, allow_float_scores=False)`.

### 20-types-overview-R17
- **Category:** Score validation
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Adapter returns scores conforming to parent `Eval.output_scores` shape, validated at EvalRun save time by `EvalRun.validate_scores`.
- **Spec quote:** Section 3.3 point 4: "Returns scores conforming to the parent Eval.output_scores shape (validated at EvalRun save time...)"
- **Evidence:** `eval.py:530-580` — `EvalRun.validate_scores` model_validator checks score keys match `eval.output_scores` and validates ranges per rating type.

### 20-types-overview-R18
- **Category:** LLM judge adapter
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `LlmJudgeAdapter` uses Jinja2 `prompt_template` + `JinjaInputTransform`, `required_var` pre-check via `extract()`, calls LLM, parses via `scoring_utils.build_llm_as_judge_score()` or `scoring_utils.build_g_eval_score()` depending on `g_eval` flag.
- **Spec quote:** Section 3.3 table row 1
- **Evidence:** `v2_eval_llm_judge.py:99-180` — renders prompt via `_template_env.from_string(props.prompt_template).render(...)`, checks `required_var` via `check_required_vars()`, calls LLM via adapter, and dispatches to `build_g_eval_score()` or `build_llm_as_judge_score()` based on `props.g_eval`.

### 20-types-overview-R19
- **Category:** Deterministic adapters
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Deterministic adapters (6) use `extract()` via `value_expression` on properties; pure comparison logic; no external calls.
- **Spec quote:** Section 3.3 table row 2
- **Evidence:** Verified across `v2_eval_exact_match.py`, `v2_eval_contains.py`, `v2_eval_pattern_match.py`, `v2_eval_set_check.py`, `v2_eval_tool_call_check.py`, `v2_eval_step_count_check.py` — all implement pure comparison/extraction logic without LLM calls.

### 20-types-overview-R20
- **Category:** Code eval adapter
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `CodeEvalAdapter` passes raw sources via helper lib, executes user code in `multiprocessing` child, parses returned result.
- **Spec quote:** Section 3.3 table row 3
- **Evidence:** `v2_eval_code_eval.py:42-` — `CodeEvalAdapter(BaseV2EvalBridge)` uses `_run_sandboxed_code()` which uses multiprocessing. `sandbox_worker.py` handles the child process execution.

### 20-types-overview-R21
- **Category:** Scoring extraction
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Score token mapping (`score_from_token_string()`, `TOKEN_TO_SCORE_MAP`) extracted into `scoring_utils.py`.
- **Spec quote:** Section 4.1 table row 1
- **Evidence:** `eval_utils/scoring_utils.py:13-46` — `TOKEN_TO_SCORE_MAP` and `score_from_token_string()` present.

### 20-types-overview-R22
- **Category:** Scoring extraction
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Structured-output score parsing (`build_llm_as_judge_score`) extracted into `scoring_utils.py`.
- **Spec quote:** Section 4.1 table row 2
- **Evidence:** `eval_utils/scoring_utils.py:175-197` — `build_llm_as_judge_score()` function present.

### 20-types-overview-R23
- **Category:** Scoring extraction
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** G-Eval logprob pipeline (`build_g_eval_score`, `g_eval_single_metric`, `rating_token_to_score`, `raw_output_from_logprobs`, `metric_offsets`, `token_search_range`) extracted into `scoring_utils.py`.
- **Spec quote:** Section 4.1 table row 3
- **Evidence:** `eval_utils/scoring_utils.py:49-234` — all six functions present: `raw_output_from_logprobs` (49), `metric_offsets` (63), `token_search_range` (84), `rating_token_to_score` (101), `g_eval_single_metric` (145), `build_g_eval_score` (200).

### 20-types-overview-R24
- **Category:** Scoring extraction
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `build_score_schema()` stays on `BaseEval` (not extracted to scoring_utils).
- **Spec quote:** Section 4.1: "Also stays on BaseEval (not extracted): build_score_schema()"
- **Evidence:** `base_eval.py:134-214` — `build_score_schema()` remains as a classmethod on `BaseEval`.

### 20-types-overview-R25
- **Category:** Scoring extraction
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** GEvalTask construction, generate_*_run_description, and model_and_provider are NOT extracted into scoring_utils (never shared with V2).
- **Spec quote:** Section 4.2 table
- **Evidence:** `g_eval.py:42-87` (GEvalTask), `g_eval.py:121-247` (generate methods) remain in g_eval.py. `model_and_provider_from_config` is in `base_eval.py`, not `scoring_utils.py`.

### 20-types-overview-R26
- **Category:** Consumption pattern
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** V2 LlmJudgeAdapter imports and uses `build_llm_as_judge_score` and `build_g_eval_score` from scoring_utils.
- **Spec quote:** Section 4.3 first code block
- **Evidence:** `v2_eval_llm_judge.py:19-26` — imports `build_g_eval_score`, `build_llm_as_judge_score` from `scoring_utils`. Lines 167-178 call them based on `props.g_eval`.

### 20-types-overview-R27
- **Category:** Consumption pattern
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Legacy GEval imports scoring functions from scoring_utils (unchanged beyond import path).
- **Spec quote:** Section 4.3 second code block
- **Evidence:** `g_eval.py:9-26` — GEval imports all scoring functions from `scoring_utils`. Methods at lines 336-368 delegate to them. The imports use aliased names (e.g., `_score_from_token_string`) but functionally identical.

### 20-types-overview-R28
- **Category:** Characterization tests
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** Two characterization tests must land before extraction: `test_generate_ref_ans_run_description` and `test_run_eval_reference_answer_data_type`.
- **Spec quote:** Section 4.4: "Two characterization tests (~50 LOC) pinning current behavior must land..."
- **Evidence:** `test_g_eval_characterization.py` exists but contains tests for `build_llm_as_judge_score` and `build_g_eval_score` scoring methods. It does NOT contain `test_generate_ref_ans_run_description` or `test_run_eval_reference_answer_data_type`. The extraction already happened, so the "hard gate" was apparently bypassed.
- **Divergence:** The spec-mandated specific tests for the reference_answer path are absent. Different characterization tests were written (for scoring methods), which is useful but doesn't cover the zero-test-coverage gap the spec identified.

### 20-types-overview-R29
- **Category:** Extensibility
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Catalog is closed for V2.0 — no runtime plugin discovery, no setuptools entry-point registration.
- **Spec quote:** Section 5.1: "V2EvalType enum and V2EvalConfigProperties union are closed for V2.0"
- **Evidence:** `eval.py:67-78` — enum is a static `str, Enum`. `registry.py:25-34` — `_V2_ADAPTER_MAP` is a static dict. No plugin discovery mechanism.

### 20-types-overview-R30
- **Category:** Frontend registry
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Frontend mirrors dispatch with create-form-by-type and result-renderer-by-type registries, exhaustive over V2EvalType.
- **Spec quote:** Section 2.4: "The frontend mirrors this dispatch with two parallel registries... Both are exhaustive over V2EvalType"
- **Evidence:** `app/web_ui/src/lib/utils/eval_types/registry.ts:72-157` — `getV2EvalTypeMetadata()` switch covers all 8 types with `assertNever(type)` default for compile-time exhaustiveness. Returns `createFormComponent` and `resultRendererComponent` for each type.

### 20-types-overview-R31
- **Category:** Adapter return type
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** V2 adapters return scores as `EvalScores` plus optional skipped_reason and skipped_detail (a tuple).
- **Spec quote:** Section 3.3 + focus notes: "Adapter return tuple (scores, skipped_reason, skipped_detail)"
- **Evidence:** `base_eval.py:241-243` — `evaluate()` abstract method returns `tuple[EvalScores, SkippedReason | None, str | None]`. Verified in all 8 V2 adapters.

### 20-types-overview-R32
- **Category:** SpecType mapping
- **Verdict:** CANNOT_VERIFY
- **Severity:** minor
- **Requirement:** For V2.0, all 17 existing SpecTypes in the builder/Copilot flow map to `llm_judge`.
- **Spec quote:** Section 1: "SpecType mapping (K.4): For V2.0, all 17 existing SpecTypes in the builder/Copilot flow map to llm_judge."
- **Evidence:** This is a UI/flow mapping that would be implemented in the builder/Copilot frontend. Would require tracing through the builder components to verify. Not directly visible in the backend code reviewed.

---

## Deferred/Cut Items

### 20-types-overview-D01
- **Verdict:** DEFERRED_OK
- **Requirement:** Post-V2 types (`composite`, `threshold`, `json_schema`, `event_ordering`, `embedding_similarity`, `dag_metric`) are not in the V2.0 enum.
- **Spec quote:** Section 1: "Post-V2 types (not in V2.0 enum)"
- **Evidence:** None of these values appear in `V2EvalType` enum. Correctly omitted.

### 20-types-overview-D02
- **Verdict:** DEFERRED_OK
- **Requirement:** Mapping SpecTypes to deterministic/code types (e.g. `appropriate_tool_use` to `tool_call_check`) is deferred to post-V2.
- **Spec quote:** Section 1: "Mapping other SpecTypes to deterministic or code types... is deferred"
- **Evidence:** No such mapping exists in code. Correctly deferred.

---

## Verifier-Added Requirements (source: verifier_added)

### 20-types-overview-V01
- **Category:** Adapter contract
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** The `evaluate()` method on V2 adapters should accept `EvalTaskInput` (not raw `TaskRun`).
- **Spec quote:** Section 3.3 point 2 + Section 3.1 inheritance diagram mentions V2 adapters receive EvalInput
- **Evidence:** `base_eval.py:241-243` — `evaluate(self, eval_input: EvalTaskInput)` accepts `EvalTaskInput`. The bridge at line 248 converts `TaskRun` to `EvalTaskInput`.

### 20-types-overview-V02
- **Category:** File organization
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `scoring_utils.py` should be located at `kiln_ai/adapters/eval/scoring_utils.py`.
- **Spec quote:** Section 4.1: "extracted into `kiln_ai/adapters/eval/scoring_utils.py`"
- **Evidence:** Actual location is `kiln_ai/adapters/eval/eval_utils/scoring_utils.py` — nested one level deeper in an `eval_utils` subdirectory. This is a minor organizational difference; the file exists and is correctly used. Functionally equivalent.
- **Note:** Marking MET as the spec path was illustrative ("e.g.") and the actual path is a reasonable organizational choice.
