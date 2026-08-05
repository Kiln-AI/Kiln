---
status: complete
---

# Phase 1: Backend -- contract, helpers, validators, reasoning capture

## Overview

Replace the 3-tuple return from all V2 `evaluate()` adapters with a typed `V2EvalResult` model, fix the two broken `KilnEvalHelpers` trace-navigation methods, add four save-time validators, and wire judge reasoning through to `EvalRun.intermediate_outputs`. All changes are in `libs/core` and the desktop API layer.

## Steps

### 1. Add `V2EvalResult` model (eval.py)

Add `V2EvalResult(BaseModel)` next to `EvalTaskInput` in `libs/core/kiln_ai/datamodel/eval.py`:
```python
class V2EvalResult(BaseModel):
    scores: EvalScores = Field(default_factory=dict)
    skipped_reason: SkippedReason | None = None
    skipped_detail: str | None = None
    intermediate_outputs: dict[str, str] | None = None
```

### 2. Migrate `BaseV2EvalBridge.evaluate` signature (base_eval.py)

Change `evaluate` return type from `tuple[EvalScores, SkippedReason | None, str | None]` to `V2EvalResult`. Update `run_eval` to destructure from `V2EvalResult`:
```python
result = await self.evaluate(eval_task_input)
if result.skipped_reason is not None:
    raise ValueError(...)
return result.scores, result.intermediate_outputs
```

### 3. Migrate all 8 V2 adapter `evaluate()` returns

Each adapter: change return type annotation to `V2EvalResult`, wrap return values in `V2EvalResult(...)`.
- `v2_eval_llm_judge.py`: carry `run_output.intermediate_outputs` through
- `v2_eval_code_eval.py`, `v2_eval_exact_match.py`, `v2_eval_contains.py`, `v2_eval_pattern_match.py`, `v2_eval_set_check.py`, `v2_eval_tool_call_check.py`, `v2_eval_step_count_check.py`: mechanical wrapping

### 4. Migrate 3 consumer call sites in `eval_runner.py`

In `_run_v2_job`, update the 3 branches that call `evaluator.evaluate(...)`:
- `from_eval_input` (~line 463)
- `task_run_eval` (~line 489)
- `eval_config_eval` (~line 520)

Each: destructure from `V2EvalResult`, add `intermediate_outputs=result.intermediate_outputs` to `EvalRun` construction.

### 5. Migrate `eval_api.py` consumer (`test_v2_eval`)

Update `test_v2_eval` endpoint to destructure from `V2EvalResult`, add `intermediate_outputs` to `TestV2EvalResponse`.

### 6. Update conftest stubs

Update `StubV2Eval` and `SkippingStubV2Eval` in `conftest.py` to return `V2EvalResult`.

### 7. D14/D15 -- Rewrite `eval_helpers.py` methods

- `get_tool_calls`: iterate `role=="assistant"` messages, flatten `tool_calls` to `{name, arguments, id}` (mirroring `v2_eval_tool_call_check.py` logic)
- `get_assistant_messages`: return `list[str]` (content strings), omit `content: null` turns
- Add `import json`

### 8. D27 -- `expected_tools` non-empty validator

Add `expected_tools: list[ToolCallSpec] = Field(min_length=1)` to `ToolCallCheckProperties`.

### 9. D28 -- `ArgMatch` regex compiled at save

Add `model_validator(mode="after")` to `ArgMatch`: when `match_mode == "regex"`, call `re.compile(str(self.value))`.

### 10. D29 -- `reference_key` min_length=1

Change `reference_key: str | None = None` to `reference_key: str | None = Field(default=None, min_length=1)` on `ExactMatchProperties`, `ContainsProperties`, `SetCheckProperties`.

### 11. D30 -- AST-based useless-template check

In `EvalConfig.validate_v2_templates_and_expressions`, replace the `{{` surface scan with `jinja2.meta.find_undeclared_variables` AST check requiring at least one of `{final_message, trace, task_input}`.

## Tests

### Existing test updates
- `test_eval_helpers.py`: update `_SAMPLE_TRACE` to use OpenAI-format tool calls; update `test_get_assistant_messages` to assert `list[str]`; update `test_get_tool_calls` to assert `{name, arguments, id}` shape
- `test_code_eval_samples.py:294`: update synthetic trace to OpenAI format
- `test_v2_dispatch_and_contract.py`: update stubs to use `V2EvalResult`

### New tests
- `test_eval_helpers.py`: real-format fixture with `role:"assistant"` + nested `tool_calls`; tests for `content: null` omission, malformed tool calls
- `test_eval_model.py` or inline: D27 empty `expected_tools` rejected; D28 bad regex rejected; D29 `reference_key=""` rejected, `None` accepted; D30 `reference_data`-only and literal templates rejected, `final_message`/`trace`/`task_input` templates accepted
- Verify `V2EvalResult` construction and field access
