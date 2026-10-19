---
status: complete
---

# Phase 1: Prereqs + Additive Schema Foundation

## Overview

This phase builds the data model foundation for V2 evals. It has three parts:

1. **V1 bug fix:** Fix `validate_template_properties` to allow non-template Evals (components/15 section 4.3).
2. **Thinking formatter fix:** Add opt-in `forward_thinking_instructions` to `SingleTurnR1ThinkingFormatter` (components/05).
3. **Additive schema changes:** Extend `EvalConfigType`, `EvalConfig`, `Eval`, `EvalRun` with V2 fields; add `EvalInput` model; add `EvalInputFilter` protocol/registry; refactor `eval_adapter_from_type` dispatch signature (components/10, 15).

All changes are additive. V1 behavior is unchanged for existing records and callers.

## Steps

### Step 1: Fix `validate_template_properties` bug (eval.py)

Guard the validator to return early when `template is None`:

```python
@model_validator(mode="after")
def validate_template_properties(self) -> Self:
    if self.template is None:
        return self
    # ... rest unchanged ...
```

### Step 2: Thinking formatter fix (chat_formatter.py)

**SingleTurnR1ThinkingFormatter.__init__:** Add `forward_thinking_instructions: bool = False` parameter.

**SingleTurnR1ThinkingFormatter.next_turn:** When `forward_thinking_instructions=True` and `self.thinking_instructions` is set, append thinking instructions to the user message using the same pattern as `TwoMessageCotFormatter`.

**get_chat_formatter:** Pass `thinking_instructions` through for `single_turn_r1_thinking` case; add `forward_thinking_instructions` param.

Add deprecation warning when thinking_instructions are silently dropped.

### Step 3: V2 enum + properties types (eval.py)

Add `v2 = "v2"` to `EvalConfigType`.

Add `V2EvalType` enum with all 8 types.

Add per-type properties BaseModel classes: `LlmJudgeProperties`, `ExactMatchProperties`, `PatternMatchProperties`, `ContainsProperties`, `SetCheckProperties`, `ToolCallCheckProperties`, `StepCountCheckProperties`, `CodeEvalProperties`.

Add helper models: `ArgMatch`, `ToolCallSpec`, `UserMessage`, `SingleTurnEvalInputData`, `MultiTurnSyntheticEvalInputData`, `EvalInputData` union.

Add `V2EvalConfigProperties` discriminated union.

Add `SkippedReason` enum.

### Step 4: EvalConfig schema changes (eval.py)

- `model_name: str | None = None`
- `model_provider: str | None = None`
- `properties: V2EvalConfigProperties | dict[str, Any] | None = None`
- Add `dispatch_properties_parsing` mode="before" validator
- Extend `validate_properties` with V2 branch
- Guard `validate_json_serializable` for V2

### Step 5: Eval schema changes (eval.py)

- `evaluation_data_type: EvalDataType | None = None` (optional)
- `eval_set_filter_id: DatasetFilterId | None = None` (optional)
- Add `eval_input_filter_id: EvalInputFilterId | None = None`
- Add `validate_filter_fields` mutual-exclusivity validator

### Step 6: EvalRun schema changes (eval.py)

- `dataset_id: ID_TYPE | None = None` (optional, was required)
- `output: str | None = None` (optional for skipped runs)
- Add `eval_input_id: ID_TYPE | None = None`
- Add `reference_data: dict[str, JsonValue] | None = None`
- Add `skipped_reason: str | None = None`
- Add `skipped_detail: str | None = None`
- Add `validate_input_source` XOR validator
- Extend `validate_output_fields` with V2 bypass
- Extend `validate_scores` to allow empty scores when skipped
- Extend `validate_reference_answer` with V2 bypass

### Step 7: EvalInput model (new file or in eval.py)

New `KilnParentedModel` with `tags`, `reference`, and discriminated `data` field.

### Step 8: Task.parent_of extension (task.py)

Add `"eval_inputs": EvalInput` to `Task.parent_of`.

### Step 9: EvalInputFilter (dataset_filters.py)

Add `EvalInputFilter` protocol, `EvalInputFilterId` type, `eval_input_filter_from_id` registry, `AllEvalInputFilter`, `TagEvalInputFilter`.

### Step 10: Registry dispatch refactor (registry.py)

Change `eval_adapter_from_type` signature from `EvalConfigType` to `EvalConfig`. Add V2 dispatch stub. Update call site in `eval_runner.py`.

### Step 11: `model_and_provider` helper extraction (base_eval.py)

Extract `model_and_provider()` to a standalone function so V2 non-LLM adapters can skip it. Keep existing method as a thin wrapper for V1 compat.

## Tests

### Thinking formatter tests (test_chat_formatter.py)
- `test_r1_thinking_forward_true`: forward_thinking_instructions=True appends thinking_instructions to user message
- `test_r1_thinking_forward_false_default`: default drops thinking_instructions (legacy behavior)
- `test_r1_thinking_forward_conversation_history`: conversation_history input skips `<user_input>` wrapping
- `test_r1_thinking_forward_no_instructions`: thinking_instructions=None with forward=True produces no crash
- `test_r1_thinking_deprecation_warning`: DeprecationWarning fires when instructions dropped
- `test_get_chat_formatter_r1_passes_thinking_instructions`: get_chat_formatter passes thinking_instructions through

### V2 EvalConfig tests (test_eval_model.py)
- `test_v2_eval_config_valid`: valid V2 config with typed properties
- `test_v2_eval_config_rejects_root_model_fields`: V2 with root model_name/provider fails
- `test_v2_eval_config_requires_typed_properties`: V2 with dict properties fails
- `test_legacy_config_unchanged`: existing g_eval config works as before
- `test_legacy_config_requires_model_fields`: legacy config with None model_name fails
- `test_v2_json_serializable_bypass`: V2 config skips json.dumps check

### V2 Eval tests (test_eval_model.py)
- `test_eval_v2_with_eval_input_filter`: V2 eval with eval_input_filter_id
- `test_eval_filter_mutual_exclusivity`: both or neither filter set raises
- `test_eval_optional_evaluation_data_type`: evaluation_data_type=None succeeds
- `test_validate_template_properties_none_template`: template=None skips validation

### V2 EvalRun tests (test_eval_model.py)
- `test_eval_run_v2_with_eval_input_id`: V2 run with eval_input_id
- `test_eval_run_input_source_xor`: both or neither source raises
- `test_eval_run_skipped_allows_empty_scores`: skipped run with empty scores
- `test_eval_run_v2_bypass_output_fields`: V2 config bypasses legacy output field validation
- `test_eval_run_skipped_allows_none_output`: skipped run with output=None

### EvalInput tests (test_eval_model.py)
- `test_eval_input_single_turn`: valid single-turn EvalInput
- `test_eval_input_with_reference`: EvalInput with reference dict
- `test_eval_input_with_tags`: EvalInput with tags
- `test_eval_input_persists_under_task`: save/load from disk under Task

### EvalInputFilter tests (test_dataset_filters.py or new)
- `test_all_eval_input_filter`: AllEvalInputFilter always returns True
- `test_tag_eval_input_filter`: TagEvalInputFilter matches tags
- `test_eval_input_filter_id_validation`: valid/invalid filter IDs
- `test_eval_input_filter_from_id_registry`: registry returns correct filters

### Registry tests
- `test_eval_adapter_from_type_legacy`: legacy dispatch unchanged
- `test_eval_adapter_from_type_v2_stub`: V2 dispatch raises NotImplementedError (adapters not yet built)

### Characterization tests for existing V1 paths
- `test_v1_eval_config_loads_from_disk`: V1 config round-trips to disk
- `test_v1_eval_run_with_reference_answer`: V1 reference_answer path works
