# Spec-Fidelity Review: Unit 10 — Data Model

Requirements: 62 total — MET 55, PARTIAL 3, MISSING 2, CONTRADICTED 1, DEFERRED_OK 1, CANNOT_VERIFY 0

---

## Requirement Table

### Eval (Section 1)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R01 | field | MET | — | Eval has `name: FilenameString` | §1 schema | eval.py:754 `name: FilenameString` | — |
| 10-R02 | field | MET | — | Eval has `description: str \| None = None` | §1 schema | eval.py:755-756 `description: str \| None = Field(default=None, ...)` | — |
| 10-R03 | field | MET | — | Eval has `template: EvalTemplateId \| None = None` | §1 schema | eval.py:758-761 | — |
| 10-R04 | field | MET | — | Eval has `current_config_id: ID_TYPE = None` | §1 schema | eval.py:762-765 | — |
| 10-R05 | field | MET | — | Eval has `output_scores: list[EvalOutputScore]` with at least one required | §1 schema + validator | eval.py:782-783, eval.py:890-902 `validate_scores` | — |
| 10-R06 | field | MET | — | Eval has `favourite: bool = False` | §1 schema | eval.py:785-788 | — |
| 10-R07 | field | MET | — | Eval has `template_properties: dict[str, str \| int \| bool \| float] \| None = None` | §1 schema | eval.py:789-792 | — |
| 10-R08 | field | MET | — | `eval_set_filter_id: DatasetFilterId \| None = Field(default=None)` | §1 schema, "CHANGED: optional in V2" | eval.py:766-769 | — |
| 10-R09 | field | MET | — | `eval_configs_filter_id: DatasetFilterId \| None = None` | §1 schema | eval.py:770-773 | — |
| 10-R10 | field | MET | — | `train_set_filter_id: DatasetFilterId \| None = None` | §1 schema | eval.py:774-776 | — |
| 10-R11 | field | MET | — | `eval_input_filter_id: EvalInputFilterId \| None = Field(default=None)` (NEW per A2.5/A2.9) | §1 schema | eval.py:778-781 | — |
| 10-R12 | field/default | CONTRADICTED | major | `evaluation_data_type: EvalDataType \| None = None` — spec says default is `None` | §1 schema: "CHANGED per A2.3: optional in V2 definition." and default shown as `= None` | eval.py:793-795 `default=EvalDataType.final_answer` | Code defaults to `EvalDataType.final_answer` instead of `None`. This means V2 evals created without setting this field get the V1 default rather than None as the spec requires. |
| 10-R13 | validator | MET | — | `validate_filter_fields`: exactly one of `eval_set_filter_id` / `eval_input_filter_id` must be set | §1 schema validator A2.9 | eval.py:904-912 | — |
| 10-R14 | design | MET | — | 1:1 cardinality: one Eval has one operative EvalConfig via `current_config_id` | §1.1 C.9 | Field exists, no multi-config dispatch logic. | — |
| 10-R15 | design | MET | — | Multi-signal = `output_scores` within one config, not multi-config | §1.2 "Different scoring approaches = different Evals" | Structural design, enforced by `output_scores` on Eval | — |

### EvalOutputScore (Section 1.2)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R16 | field | MET | — | `name: FilenameStringShort` (max 32 chars) | §1.2 schema | eval.py:382-384 | — |
| 10-R17 | field | MET | — | `instruction: str \| None = None` | §1.2 schema | eval.py:386-389 | — |
| 10-R18 | field | MET | — | `type: TaskOutputRatingType` (five_star / pass_fail / pass_fail_critical) | §1.2 schema | eval.py:390-391 | — |
| 10-R19 | method | MET | — | `json_key()` converts name to snake_case | §1.2 | eval.py:393-399 `string_to_json_key(self.name)` | — |
| 10-R20 | validator | MET | — | Custom rating types explicitly forbidden | §1.2 "Custom rating types remain explicitly forbidden" | eval.py:401-407 `validate_type` raises on `TaskOutputRatingType.custom` | — |

### EvalConfig (Section 2)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R21 | enum | MET | — | `EvalConfigType` has values: `g_eval`, `llm_as_judge`, `v2` | §2.1 schema | eval.py:59-65 | — |
| 10-R22 | field | MET | — | `EvalConfig.name: FilenameString` | §2.1 schema | eval.py:617 | — |
| 10-R23 | field | MISSING | minor | `EvalConfig.description: str \| None = None` | §2.1 schema: `description: str \| None = None` | eval.py:610-633 — no `description` field defined. Not inherited from KilnParentedModel or KilnBaseModel either. | Field absent from code. Not present in V1 EvalConfig either, so this is a new field the spec defines that was never implemented. |
| 10-R24 | field | MET | — | `config_type: EvalConfigType = EvalConfigType.g_eval` | §2.1 schema | eval.py:626-629 | — |
| 10-R25 | field | MET | — | `model_name: str \| None = None` (optional for V2) | §2.1 schema | eval.py:618-621 | — |
| 10-R26 | field | MET | — | `model_provider: str \| None = None` (optional for V2) | §2.1 schema | eval.py:622-625 | — |
| 10-R27 | field/type | MET | — | `properties: V2EvalConfigProperties \| dict[str, Any] \| None = None` | §2.1 schema | eval.py:630-633 | — |
| 10-R28 | validator | MET | — | `dispatch_properties_parsing` model_validator(mode="before") routes parsing by config_type | §2.2 A2.8 | eval.py:635-650 | — |
| 10-R29 | validator | MET | — | V2 shape validation: `v2` requires typed properties (BaseModel), must not set root-level model_name/model_provider | §2.3 A2.1 | eval.py:680-688 | — |
| 10-R30 | validator | MET | — | Legacy shape validation: `g_eval`/`llm_as_judge` require model_name, model_provider, dict properties | §2.3 | eval.py:662-679 | — |
| 10-R31 | design | MET | — | Adapter registry takes full `EvalConfig` (not enum) | §2.5 A2.11 | registry.py:37 `legacy_eval_adapter_from_type(eval_config: EvalConfig)` and registry.py:55-56 `v2_eval_adapter_from_config(eval_config: EvalConfig, ...)` | — |
| 10-R32 | validator | MET | — | `validate_json_serializable` bypassed for V2 | §2.3 "extended with a V2 bypass" | eval.py:730-740 returns early when `config_type == EvalConfigType.v2` | — |

### V2EvalType and V2EvalConfigProperties (Section 3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R33 | enum | MET | — | V2EvalType has 8 values: llm_judge, exact_match, pattern_match, set_check, tool_call_check, contains, step_count_check, code_eval | §3.1 | eval.py:67-78 — all 8 values present | — |
| 10-R34 | type/union | MET | — | V2EvalConfigProperties is Annotated[Union[...8 classes...], Discriminator("type")] | §3.2 | eval.py:226-238 — all 8 classes in union with `Discriminator("type")` | — |

### LlmJudgeProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R35 | field | MET | — | `type: Literal[V2EvalType.llm_judge] = V2EvalType.llm_judge` | §3.3 LlmJudgeProperties | eval.py:82 | — |
| 10-R36 | field | MET | — | `model_name: str`, `model_provider: str` (required, on properties not root) | §3.3 per A2.10 | eval.py:83-84 | — |
| 10-R37 | field | MET | — | `system_prompt: str \| None = None` | §3.3 | eval.py:85 | — |
| 10-R38 | field | MET | — | `prompt_template: str` (required) | §3.3 | eval.py:86 | — |
| 10-R39 | field | MET | — | `required_var: list[str] = []` | §3.3 | eval.py:87 | — |
| 10-R40 | field | MET | — | `thinking_instruction: str \| None = None` | §3.3 | eval.py:88 | — |
| 10-R41 | field | MET | — | `g_eval: bool = False` | §3.3 "renamed from g_eval_mode per A2.2" | eval.py:89 | — |

### ExactMatchProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R42 | field | MET | — | Fields: type, value_expression, expected_value, reference_key per spec | §3.3 ExactMatchProperties | eval.py:92-96 | — |
| 10-R43 | validator | MET | — | Exactly one of expected_value / reference_key required | §3.3 | eval.py:99-105 | — |

### PatternMatchProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R44 | field | MET | — | Fields: type, value_expression, pattern (required), mode Literal["must_match", "must_not_match"] = "must_match" | §3.3 PatternMatchProperties | eval.py:108-112 | — |

### ContainsProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R45 | field | MET | — | Fields: type, value_expression, substring, reference_key per spec | §3.3 ContainsProperties | eval.py:125-129 | — |
| 10-R46 | validator | MET | — | Exactly one of substring / reference_key required | §3.3 | eval.py:133-136 | — |

### SetCheckProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R47 | field | MET | — | Fields: type, value_expression, expected_set, reference_key, mode Literal["subset","superset","equal"] = "subset" | §3.3 SetCheckProperties | eval.py:140-145 | — |
| 10-R48 | validator | MET | — | Exactly one of expected_set / reference_key required | §3.3 | eval.py:147-151 | — |

### ToolCallCheckProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R49 | field | MET | — | ArgMatch: `value: JsonValue`, `match_mode: Literal["exact","contains","regex"] = "exact"` | §3.3 | eval.py:154-156 | — |
| 10-R50 | field | MET | — | ToolCallSpec: `tool_name: str`, `expected_args: dict[str, ArgMatch] \| None = None` | §3.3 | eval.py:159-161 | — |
| 10-R51 | field | MET | — | ToolCallCheckProperties: type, expected_tools, match_mode Literal["any","all","ordered","never"] = "all", on_unexpected_tools Literal["ignore","fail"] = "ignore" | §3.3 | eval.py:164-168 | — |

### StepCountCheckProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R52 | field | MET | — | Fields: type, count_type Literal["tool_calls","model_responses","turns"], min_count/max_count int \| None = None | §3.3 | eval.py:171-175 | — |
| 10-R53 | validator | MET | — | At least one of min_count/max_count required; min_count <= max_count | §3.3 validator | eval.py:177-189 | — |

### CodeEvalProperties (Section 3.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R54 | field | MET | — | `type: Literal[V2EvalType.code_eval] = V2EvalType.code_eval`, `code: str` | §3.3 CodeEvalProperties | eval.py:192-194 | — |

### EvalInput (Section 4)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R55 | class | MET | — | EvalInput is a KilnParentedModel | §4.1 schema | eval.py:289 `class EvalInput(KilnParentedModel)` | — |
| 10-R56 | field | MET | — | `tags: list[str] = []` | §4.1 | eval.py:303-306 `tags: list[str] = Field(default_factory=list, ...)` | — |
| 10-R57 | field | MET | — | `reference: dict[str, JsonValue] \| None = None` | §4.1, §4.4 | eval.py:299-302 | — |
| 10-R58 | field | MET | — | `data: EvalInputData` (discriminated union) | §4.1 | eval.py:296-298 | — |
| 10-R59 | negative | DEFERRED_OK | — | `source_task_run_id` is NOT included in V2, deferred to Feedback Pipeline project | §4.1 "NOTE: source_task_run_id is NOT included" | Not present in eval.py EvalInput class. Correctly omitted. | — |
| 10-R60 | registration | MET | — | EvalInput registered as child of Task: `"eval_inputs": EvalInput` in parent_of | §4.1 | task.py:137 `"eval_inputs": EvalInput` | — |

### EvalInputData discriminated union (Section 4.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R61 | type/union | MET | — | EvalInputData = Annotated[Union[SingleTurnEvalInputData, MultiTurnSyntheticEvalInputData], Discriminator("type")] | §4.3 | eval.py:280-286 | — |

### SingleTurnEvalInputData (Section 4.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R62 | field | MET | — | `type: Literal["single_turn"] = "single_turn"`, `user_message: UserMessage` | §4.3 | eval.py:269-271 | — |
| 10-R63 | class | MET | — | `UserMessage` has `text: str` | §4.3 | eval.py:265-266 | — |

### MultiTurnSyntheticEvalInputData (Section 4.3)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R64 | field | MET | — | `type: Literal["multi_turn_synthetic"] = "multi_turn_synthetic"` | §4.3 | eval.py:275 | — |
| 10-R65 | field | MET | — | `first_message: UserMessage \| None = None` | §4.3 | eval.py:276 | — |
| 10-R66 | field/type | PARTIAL | minor | `synthetic_user_info: SyntheticUserInfo` — spec says typed Pydantic model | §4.3 "SyntheticUserInfo is a typed Pydantic model (not a flat dict). Its field list is owned by the parallel multi-turn-synthetic project (C.5)." | eval.py:277 `synthetic_user_info: dict[str, JsonValue] = {}` | Code uses a flat dict instead of a typed Pydantic model. The spec explicitly says "typed Pydantic model (not a flat dict)". However, the spec also says the field list is owned by the parallel multi-turn-synthetic project, which may not be implemented yet. |

### EvalRun (Section 5)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R67 | field | MET | — | `dataset_id: ID_TYPE \| None = None` (CHANGED: optional) | §5.1 | eval.py:421-423 `default=None` | — |
| 10-R68 | field | MET | — | `task_run_config_id: ID_TYPE \| None` | §5.1 | eval.py:425-427 | — |
| 10-R69 | field | MET | — | `eval_config_eval: bool = False` (unchanged) | §5.1 | eval.py:428-430 | — |
| 10-R70 | field | MET | — | `input: str` | §5.1 | eval.py:432-434 | — |
| 10-R71 | field | MET | — | `output: str \| None = None` (optional for skipped runs) | §5.1 | eval.py:435-438 | — |
| 10-R72 | field | MET | — | `reference_answer: str \| None = None` (unchanged V1) | §5.1 | eval.py:439-442 | — |
| 10-R73 | field | MET | — | `intermediate_outputs: dict[str, str] \| None = None` | §5.1 | eval.py:443-445 | — |
| 10-R74 | field | MET | — | `task_run_trace: str \| None = None` | §5.1 | eval.py:447-449 | — |
| 10-R75 | field | PARTIAL | minor | `scores: EvalScores` — spec shows no default | §5.1 `scores: EvalScores # Dict[str, float]` | eval.py:451-453 `scores: EvalScores = Field(default={}, ...)` | Code has `default={}` while spec shows no default. Functionally compatible with skip behavior (empty scores for skipped runs), but technically adds a default the spec doesn't show. |
| 10-R76 | field | MET | — | `task_run_usage: Usage \| None = None` | §5.1 | eval.py:455-458 | — |
| 10-R77 | field | MET | — | `eval_input_id: ID_TYPE \| None = None` (NEW per A2.6) | §5.1 | eval.py:460-463 | — |
| 10-R78 | field | MET | — | `reference_data: dict[str, JsonValue] \| None = None` (NEW per A2.7) | §5.1 | eval.py:464-467 | — |
| 10-R79 | field | MET | — | `skipped_reason: str \| None = None` (NEW per E.18) | §5.1 | eval.py:468-471 | — |
| 10-R80 | field | MET | — | `skipped_detail: str \| None = None` (NEW per E.18) | §5.1 | eval.py:472-475 | — |

### EvalRun Validators (Section 5.2-5.5)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R81 | validator | MET | — | `validate_input_source`: exactly one of dataset_id / eval_input_id | §5.2 | eval.py:482-489 | — |
| 10-R82 | validator | MET | — | `validate_output_fields` V2 bypass: early return when config_type is v2 | §5.5 C.runner.2 | eval.py:491-495 | — |
| 10-R83 | validator | MET | — | `validate_scores` skips validation when `skipped_reason is not None` | §5.4 "when skipped_reason is not None, allow empty/None scores" | eval.py:531-533 early return when `self.skipped_reason is not None` | — |
| 10-R84 | validator | MET | — | `validate_reference_answer` V2 bypass | §5.3 "existing validate_reference_answer validator stays as-is (gates only reference_answer)" | eval.py:589-607 returns early for V2 configs | — |

### SkippedReason Enum (Section 5.4)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R85 | enum | MET | — | SkippedReason has 6 values: missing_reference_key, extraction_failed, missing_trace, incompatible_input_shape, code_eval_not_trusted, type_not_available | §5.4 | eval.py:254-262 — all 6 values present | — |

### EvalConfig description field (Section 2.1) — Missing

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-R23 | field | MISSING | minor | See above | — | — | — |

---

## Verifier-Added Requirements (re-scan)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 10-V01 | field/default | PARTIAL | minor | Eval `evaluation_data_type` default should be `None` for V2 | §1 schema: `evaluation_data_type: EvalDataType \| None = None` — the `= None` in spec means default None | eval.py:793-794 `default=EvalDataType.final_answer` | Already captured as 10-R12 (CONTRADICTED). Not double-counted here. |

No additional binding requirements found in re-scan beyond those already captured.

---

## Summary

- **CONTRADICTED (1):** `Eval.evaluation_data_type` defaults to `EvalDataType.final_answer` instead of spec-required `None` (10-R12). This means V2 evals incorrectly inherit a V1 data type by default.
- **MISSING (2):** `EvalConfig.description` field absent from code (10-R23); spec explicitly shows it as `str | None = None`.
- **PARTIAL (3):** `MultiTurnSyntheticEvalInputData.synthetic_user_info` uses `dict[str, JsonValue]` instead of a typed Pydantic model (10-R66). `EvalRun.scores` has `default={}` not shown in spec (10-R75, minor). `Eval.evaluation_data_type` default divergence is primarily captured as CONTRADICTED.
- **DEFERRED_OK (1):** `source_task_run_id` correctly omitted from EvalInput (10-R59).
- **MET (55):** All other fields, types, defaults, enums, validators, and structural requirements match the spec.
