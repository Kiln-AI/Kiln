---
status: complete
---

# Phase 3: Deterministic + Agent Eval Types

## Overview

Implement six concrete `BaseV2Eval` adapters (exact_match, pattern_match, contains, set_check, tool_call_check, step_count_check) and register them in `_V2_ADAPTER_MAP` so the Phase 2 dispatch infrastructure routes V2 eval configs to working evaluators.

All six types are **deterministic** (no LLM calls). They consume the `EvalTaskInput` namespace assembled by the Phase 2 runner, use the shared extraction helpers in `v2_eval_helpers.py`, and return binary 1.0/0.0 scores written to **every** declared score key. The first four types operate on extracted string values; the last two walk the conversation trace.

### Key Contracts

- **Return-based skip**: Adapters return `({}, SkippedReason.xxx, "detail")` when they cannot evaluate. They never raise exceptions for skip conditions.
- **Binary scoring**: Each adapter produces a single pass/fail determination and writes the same float (1.0 or 0.0) to every key in the returned `EvalScores` dict. The runner's caller is responsible for checking score-key conformance against the parent Eval's `output_scores`.
- **Score keys**: Adapters do not know about the parent `Eval.output_scores`. They need the score keys passed to them. The `eval_config` has a `parent_eval()` method, and the parent `Eval` has `output_scores: list[EvalOutputScore]`. Each adapter reads `self.eval_config.parent_eval().output_scores` to get score keys via `json_key()`, then writes the same binary value to all keys. If `parent_eval()` returns None or has no output_scores, the adapter returns an empty `{}` scores dict (the runner/validator will handle this).
- **Trace types**: `tool_call_check` and `step_count_check` require `eval_input.trace` to be non-None. When it is None, they skip with `SkippedReason.missing_trace`.

## Steps

### Step 1: Score-key helper (`libs/core/kiln_ai/adapters/eval/eval_utils/v2_eval_helpers.py`)

Add a helper function to build a uniform binary scores dict from an eval_config:

```python
def build_binary_scores(eval_config: EvalConfig, passed: bool) -> EvalScores:
    """Build an EvalScores dict with the same binary value for all declared score keys.

    Reads output_scores from the parent Eval via eval_config.parent_eval().
    Returns {} if no parent eval or no output_scores are declared.
    """
    parent = eval_config.parent_eval()
    if parent is None or not parent.output_scores:
        return {}
    value = 1.0 if passed else 0.0
    return {score.json_key(): value for score in parent.output_scores}
```

Add the necessary imports: `EvalConfig` from `kiln_ai.datamodel.eval` and `EvalScores` from the same module.

### Step 2: Exact-match adapter (`libs/core/kiln_ai/adapters/eval/v2_eval_exact_match.py` -- new file)

Create a new file with the `ExactMatchEval` class:

```python
from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    ExactMatchProperties,
    SkippedReason,
)


class ExactMatchEval(BaseV2Eval):
    """V2 adapter for exact_match: compares an extracted value against an expected string."""

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, ExactMatchProperties)

        # 1. Extract the value to test
        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return {}, skip, detail

        # 2. Resolve expected value (from literal or reference_key)
        if props.reference_key is not None:
            expected, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return {}, skip, detail
            expected = str(expected)
        else:
            # expected_value is guaranteed non-None by the model validator
            expected = props.expected_value

        # 3. Compare
        actual = str(value)
        if props.case_sensitive:
            passed = actual == expected
        else:
            passed = actual.lower() == expected.lower() if expected is not None else False

        return build_binary_scores(self.eval_config, passed), None, None
```

### Step 3: Pattern-match adapter (`libs/core/kiln_ai/adapters/eval/v2_eval_pattern_match.py` -- new file)

```python
import re

from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    PatternMatchProperties,
    SkippedReason,
)


class PatternMatchEval(BaseV2Eval):
    """V2 adapter for pattern_match: tests an extracted value against a regex pattern."""

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, PatternMatchProperties)

        # 1. Extract the value to test
        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return {}, skip, detail

        actual = str(value)

        # 2. Run the regex (re.search for partial match).
        # The pattern is validated at save time via a model_validator that calls
        # re.compile(pattern), so invalid patterns are rejected before they reach
        # the adapter. A defensive guard is kept for safety but should never fire.
        try:
            match = re.search(props.pattern, actual)
        except re.error as e:
            return (
                {},
                SkippedReason.extraction_failed,
                f"Invalid regex pattern '{props.pattern}': {e}",
            )

        # 3. Apply mode
        if props.mode == "must_match":
            passed = match is not None
        else:  # must_not_match
            passed = match is None

        return build_binary_scores(self.eval_config, passed), None, None
```

### Step 4: Contains adapter (`libs/core/kiln_ai/adapters/eval/v2_eval_contains.py` -- new file)

```python
from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    ContainsProperties,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
)


class ContainsEval(BaseV2Eval):
    """V2 adapter for contains: checks whether the extracted value contains a substring."""

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, ContainsProperties)

        # 1. Extract the value to test
        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return {}, skip, detail

        # 2. Resolve the substring (from literal or reference_key)
        if props.reference_key is not None:
            substring, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return {}, skip, detail
            substring = str(substring)
        else:
            # substring is guaranteed non-None by the model validator
            substring = props.substring
            assert substring is not None

        # 3. Compare
        actual = str(value)
        if props.case_sensitive:
            found = substring in actual
        else:
            found = substring.lower() in actual.lower()

        # 4. Apply mode
        if props.mode == "must_contain":
            passed = found
        else:  # must_not_contain
            passed = not found

        return build_binary_scores(self.eval_config, passed), None, None
```

### Step 5: Set-check adapter (`libs/core/kiln_ai/adapters/eval/v2_eval_set_check.py` -- new file)

```python
import json

from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    SetCheckProperties,
    SkippedReason,
)


class SetCheckEval(BaseV2Eval):
    """V2 adapter for set_check: compares an extracted set against an expected set.

    The extracted value is coerced to a set of strings:
    - If it's a list, each element is stringified.
    - If it's a dict, use `set(dict.keys())`.
    - If it's a string, attempt `json.loads`; if the result is a list, stringify each element.
      Otherwise wrap the original string as a single-element set `{the_string}`.
    - Any other type: wrap as a single-element set via `{str(value)}`.
    """

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, SetCheckProperties)

        # 1. Extract the value to test
        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return {}, skip, detail

        # 2. Coerce extracted value to a set of strings
        actual_set = self._coerce_to_set(value)

        # 3. Resolve expected set (from literal or reference_key)
        if props.reference_key is not None:
            expected_raw, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return {}, skip, detail
            expected_set = self._coerce_to_set(expected_raw)
        else:
            assert props.expected_set is not None
            expected_set = set(props.expected_set)

        # 4. Compare based on mode
        if props.mode == "subset":
            # actual is a subset of expected
            passed = actual_set.issubset(expected_set)
        elif props.mode == "superset":
            # actual is a superset of expected
            passed = actual_set.issuperset(expected_set)
        else:  # equal
            passed = actual_set == expected_set

        return build_binary_scores(self.eval_config, passed), None, None

    @staticmethod
    def _coerce_to_set(value: object) -> set[str]:
        """Coerce a value to a set of strings."""
        if isinstance(value, list):
            return {str(item) for item in value}
        if isinstance(value, set):
            return {str(item) for item in value}
        if isinstance(value, dict):
            return set(value.keys())
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return {str(item) for item in parsed}
            except (json.JSONDecodeError, TypeError):
                pass
            return {value}
        return {str(value)}
```

### Step 6: Tool-call-check adapter (`libs/core/kiln_ai/adapters/eval/v2_eval_tool_call_check.py` -- new file)

This adapter inspects the conversation trace for tool calls.

**Trace structure reference**: The trace is a list of `ChatCompletionMessageParam` dicts (OpenAI format). Tool calls appear on `assistant` messages under `message["tool_calls"]`, each having `{"id": ..., "type": "function", "function": {"name": str, "arguments": str}}`. The `arguments` field is a JSON-encoded string.

```python
import json
import re
from typing import Any

from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import build_binary_scores
from kiln_ai.datamodel.eval import (
    ArgMatch,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
    ToolCallCheckProperties,
    ToolCallSpec,
)


class ToolCallCheckEval(BaseV2Eval):
    """V2 adapter for tool_call_check: validates tool calls in the trace."""

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, ToolCallCheckProperties)

        # 1. Require trace
        if eval_input.trace is None:
            return {}, SkippedReason.missing_trace, "tool_call_check requires a trace"

        # 2. Extract all tool calls from trace
        actual_calls = self._extract_tool_calls(eval_input.trace)

        # 3. Evaluate based on match_mode
        passed, unexpected_fail = self._check(
            actual_calls, props.expected_tools, props.match_mode, props.on_unexpected_tools
        )

        if not passed and unexpected_fail:
            return build_binary_scores(self.eval_config, False), None, None

        return build_binary_scores(self.eval_config, passed), None, None

    @staticmethod
    def _extract_tool_calls(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract all tool calls from the trace as a flat list.

        Each entry is {"name": str, "arguments": dict}.
        """
        calls: list[dict[str, Any]] = []
        for msg in trace:
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                continue
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, TypeError):
                    args = {}
                calls.append({"name": name, "arguments": args if isinstance(args, dict) else {}})
        return calls

    def _check(
        self,
        actual_calls: list[dict[str, Any]],
        expected_tools: list[ToolCallSpec],
        match_mode: str,
        on_unexpected: str,
    ) -> tuple[bool, bool]:
        """Check tool calls against expectations.

        Returns (passed, unexpected_fail).
        """
        if match_mode == "never":
            # No expected tools should appear in actual calls
            expected_names = {spec.tool_name for spec in expected_tools}
            for call in actual_calls:
                if call["name"] in expected_names:
                    return False, False
            return True, False

        if match_mode == "any":
            # At least one expected tool must match
            found_any = False
            for spec in expected_tools:
                for call in actual_calls:
                    if self._call_matches_spec(call, spec):
                        found_any = True
                        break
                if found_any:
                    break
            passed = found_any
        elif match_mode == "all":
            # Every expected tool must appear at least once (order-independent)
            passed = True
            for spec in expected_tools:
                found = False
                for call in actual_calls:
                    if self._call_matches_spec(call, spec):
                        found = True
                        break
                if not found:
                    passed = False
                    break
        elif match_mode == "ordered":
            # Expected tools must appear in order (but not necessarily consecutively)
            passed = self._check_ordered(actual_calls, expected_tools)
        else:
            passed = False

        # Check for unexpected tools
        unexpected_fail = False
        if passed and on_unexpected == "fail":
            expected_names = {spec.tool_name for spec in expected_tools}
            for call in actual_calls:
                if call["name"] not in expected_names:
                    passed = False
                    unexpected_fail = True
                    break

        return passed, unexpected_fail

    def _check_ordered(
        self,
        actual_calls: list[dict[str, Any]],
        expected_tools: list[ToolCallSpec],
    ) -> bool:
        """Check that expected tools appear in order within actual calls."""
        expected_idx = 0
        for call in actual_calls:
            if expected_idx >= len(expected_tools):
                break
            if self._call_matches_spec(call, expected_tools[expected_idx]):
                expected_idx += 1
        return expected_idx == len(expected_tools)

    @staticmethod
    def _call_matches_spec(call: dict[str, Any], spec: ToolCallSpec) -> bool:
        """Check if a single actual call matches a ToolCallSpec."""
        if call["name"] != spec.tool_name:
            return False
        if spec.expected_args is None:
            return True
        actual_args = call.get("arguments", {})
        for arg_name, arg_match in spec.expected_args.items():
            if arg_name not in actual_args:
                return False
            if not _arg_value_matches(actual_args[arg_name], arg_match):
                return False
        return True


def _arg_value_matches(actual: Any, arg_match: ArgMatch) -> bool:
    """Check if an actual argument value matches an ArgMatch spec."""
    if arg_match.match_mode == "exact":
        return actual == arg_match.value
    elif arg_match.match_mode == "contains":
        return str(arg_match.value) in str(actual)
    elif arg_match.match_mode == "regex":
        try:
            return re.search(str(arg_match.value), str(actual)) is not None
        except re.error:
            return False
    return False
```

### Step 7: Step-count-check adapter (`libs/core/kiln_ai/adapters/eval/v2_eval_step_count_check.py` -- new file)

```python
from typing import Any

from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import build_binary_scores
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    SkippedReason,
    StepCountCheckProperties,
)


class StepCountCheckEval(BaseV2Eval):
    """V2 adapter for step_count_check: validates the number of steps in the trace.

    count_type determines what is counted:
    - "tool_calls": total number of individual tool call invocations across all assistant messages
    - "model_responses": number of assistant messages that have non-empty content (not tool-call-only)
    - "turns": number of distinct user/assistant turn pairs (count of user messages)
    """

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, StepCountCheckProperties)

        # 1. Require trace
        if eval_input.trace is None:
            return {}, SkippedReason.missing_trace, "step_count_check requires a trace"

        # 2. Count based on count_type
        count = self._count(eval_input.trace, props.count_type)

        # 3. Check bounds
        passed = True
        if props.min_count is not None and count < props.min_count:
            passed = False
        if props.max_count is not None and count > props.max_count:
            passed = False

        return build_binary_scores(self.eval_config, passed), None, None

    @staticmethod
    def _count(trace: list[dict[str, Any]], count_type: str) -> int:
        """Count steps in the trace based on count_type."""
        if count_type == "tool_calls":
            total = 0
            for msg in trace:
                if msg.get("role") != "assistant":
                    continue
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    total += len(tool_calls)
            return total
        elif count_type == "model_responses":
            total = 0
            for msg in trace:
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content")
                if content and isinstance(content, str) and content.strip():
                    total += 1
            return total
        elif count_type == "turns":
            total = 0
            for msg in trace:
                if msg.get("role") == "user":
                    total += 1
            return total
        return 0
```

### Step 8: Register all adapters in `_V2_ADAPTER_MAP` (`libs/core/kiln_ai/adapters/eval/registry.py`)

Update `registry.py` to import all six adapter classes and populate the map:

```python
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.base_v2_eval import _V2_PROPERTY_TYPES, BaseV2Eval
from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.adapters.eval.v2_eval_contains import ContainsEval
from kiln_ai.adapters.eval.v2_eval_exact_match import ExactMatchEval
from kiln_ai.adapters.eval.v2_eval_pattern_match import PatternMatchEval
from kiln_ai.adapters.eval.v2_eval_set_check import SetCheckEval
from kiln_ai.adapters.eval.v2_eval_step_count_check import StepCountCheckEval
from kiln_ai.adapters.eval.v2_eval_tool_call_check import ToolCallCheckEval
from kiln_ai.datamodel.eval import EvalConfig, EvalConfigType, V2EvalType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseV2Eval]] = {
    V2EvalType.exact_match: ExactMatchEval,
    V2EvalType.pattern_match: PatternMatchEval,
    V2EvalType.contains: ContainsEval,
    V2EvalType.set_check: SetCheckEval,
    V2EvalType.tool_call_check: ToolCallCheckEval,
    V2EvalType.step_count_check: StepCountCheckEval,
}
```

The `v2_eval_adapter_from_config` and `eval_adapter_from_type` functions remain unchanged. Types not yet in the map (`llm_judge`, `code_eval`) will continue to hit the `NotImplementedError` / `type_not_available` skip path.

### Step 9: Update `__init__.py` (`libs/core/kiln_ai/adapters/eval/__init__.py`)

Add the new modules to the package exports:

```python
from . import (
    base_eval,
    base_v2_eval,
    eval_runner,
    g_eval,
    registry,
    v2_eval_contains,
    v2_eval_exact_match,
    v2_eval_pattern_match,
    v2_eval_set_check,
    v2_eval_step_count_check,
    v2_eval_tool_call_check,
)

__all__ = [
    "base_eval",
    "base_v2_eval",
    "eval_runner",
    "g_eval",
    "registry",
    "v2_eval_contains",
    "v2_eval_exact_match",
    "v2_eval_pattern_match",
    "v2_eval_set_check",
    "v2_eval_step_count_check",
    "v2_eval_tool_call_check",
]
```

## Tests

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_exact_match.py` (new)

Test helpers shared across this file: use `_mock_v2_eval_config` with `ExactMatchProperties` as done in `test_v2_dispatch_and_contract.py`. Build a mock `EvalConfig` that returns a mock `parent_eval()` with `output_scores` containing a single `EvalOutputScore` whose `json_key()` returns `"accuracy"`.

```python
# Helper pattern (used in all adapter test files):
def _make_eval_config(props, score_keys=("accuracy",)):
    """Build a mock EvalConfig with a parent_eval that declares score keys."""
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    parent = Mock()
    parent.output_scores = [Mock(json_key=Mock(return_value=k)) for k in score_keys]
    cfg.parent_eval = Mock(return_value=parent)
    return cfg
```

- **`test_exact_match_pass_case_sensitive`**: `expected_value="hello"`, `final_message="hello"` -> `{"accuracy": 1.0}`.
- **`test_exact_match_fail_case_sensitive`**: `expected_value="Hello"`, `final_message="hello"` -> `{"accuracy": 0.0}`.
- **`test_exact_match_pass_case_insensitive`**: `case_sensitive=False`, `expected_value="Hello"`, `final_message="hello"` -> `{"accuracy": 1.0}`.
- **`test_exact_match_from_reference_key`**: `reference_key="answer"`, `reference_data={"answer": "42"}`, `final_message="42"` -> `{"accuracy": 1.0}`.
- **`test_exact_match_missing_reference_key_skips`**: `reference_key="answer"`, `reference_data={}` -> `({}, SkippedReason.missing_reference_key, ...)`.
- **`test_exact_match_extraction_failed_skips`**: `value_expression="nonexistent"`, `final_message="x"` -> `({}, SkippedReason.extraction_failed, ...)`.
- **`test_exact_match_with_value_expression`**: `value_expression="trace[0].content"`, `expected_value="traced"`, `trace=[{"content": "traced"}]` -> `{"accuracy": 1.0}`.
- **`test_exact_match_no_parent_eval_empty_scores`**: `cfg.parent_eval` returns None -> scores is `{}`.
- **`test_exact_match_multiple_score_keys`**: Two score keys `("key_a", "key_b")` -> both get the same value in the result.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_pattern_match.py` (new)

- **`test_pattern_match_must_match_pass`**: `pattern=r"\d{3}-\d{4}"`, `final_message="call 555-1234"` -> `{"accuracy": 1.0}`.
- **`test_pattern_match_must_match_fail`**: `pattern=r"\d{3}-\d{4}"`, `final_message="no numbers here"` -> `{"accuracy": 0.0}`.
- **`test_pattern_match_must_not_match_pass`**: `mode="must_not_match"`, `pattern=r"error"`, `final_message="all good"` -> `{"accuracy": 1.0}`.
- **`test_pattern_match_must_not_match_fail`**: `mode="must_not_match"`, `pattern=r"error"`, `final_message="got an error"` -> `{"accuracy": 0.0}`.
- **`test_pattern_match_invalid_regex_rejected_at_save`**: Verify that `PatternMatchProperties(pattern="[invalid")` raises `ValidationError` (the `model_validator` calls `re.compile`). No adapter instantiation needed -- this is a datamodel-level test confirming save-time rejection.
- **`test_pattern_match_with_value_expression`**: Extract from trace, match against pattern.
- **`test_pattern_match_extraction_failed_skips`**: `value_expression="nonexistent"` -> skip.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_contains.py` (new)

- **`test_contains_must_contain_pass`**: `substring="world"`, `final_message="hello world"` -> `{"accuracy": 1.0}`.
- **`test_contains_must_contain_fail`**: `substring="missing"`, `final_message="hello world"` -> `{"accuracy": 0.0}`.
- **`test_contains_must_not_contain_pass`**: `mode="must_not_contain"`, `substring="bad"`, `final_message="hello world"` -> `{"accuracy": 1.0}`.
- **`test_contains_must_not_contain_fail`**: `mode="must_not_contain"`, `substring="hello"`, `final_message="hello world"` -> `{"accuracy": 0.0}`.
- **`test_contains_case_insensitive`**: `case_sensitive=False`, `substring="WORLD"`, `final_message="hello world"` -> `{"accuracy": 1.0}`.
- **`test_contains_from_reference_key`**: `reference_key="expected_phrase"`, `reference_data={"expected_phrase": "world"}`, `final_message="hello world"` -> `{"accuracy": 1.0}`.
- **`test_contains_missing_reference_key_skips`**: `reference_key="x"`, no reference_data -> skip.
- **`test_contains_extraction_failed_skips`**: `value_expression="nonexistent"` -> skip.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_set_check.py` (new)

- **`test_set_check_subset_pass`**: `expected_set=["a","b","c"]`, `final_message='["a","b"]'`, `mode="subset"` -> `{"accuracy": 1.0}`.
- **`test_set_check_subset_fail`**: `expected_set=["a","b"]`, `final_message='["a","b","c"]'`, `mode="subset"` -> `{"accuracy": 0.0}`.
- **`test_set_check_superset_pass`**: `expected_set=["a"]`, `final_message='["a","b"]'`, `mode="superset"` -> `{"accuracy": 1.0}`.
- **`test_set_check_superset_fail`**: `expected_set=["a","b","c"]`, `final_message='["a"]'`, `mode="superset"` -> `{"accuracy": 0.0}`.
- **`test_set_check_equal_pass`**: `expected_set=["a","b"]`, `final_message='["b","a"]'`, `mode="equal"` -> `{"accuracy": 1.0}`.
- **`test_set_check_equal_fail`**: `expected_set=["a","b"]`, `final_message='["a","c"]'`, `mode="equal"` -> `{"accuracy": 0.0}`.
- **`test_set_check_from_reference_key`**: `reference_key="expected"`, `reference_data={"expected": ["x","y"]}`, `final_message='["x","y"]'` -> pass with mode `"equal"`.
- **`test_set_check_coerce_string_no_json`**: `expected_set=["hello"]`, `final_message="hello"` (not valid JSON list) -> coerced to single-element set `{"hello"}` -> `{"accuracy": 1.0}` with mode `"equal"`.
- **`test_set_check_coerce_single_value`**: Non-list, non-string value coerced to single-element set.
- **`test_set_check_extraction_failed_skips`**: `value_expression="nonexistent"` -> skip.
- **`test_set_check_missing_reference_key_skips`**: `reference_key="x"`, no reference_data -> skip.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_tool_call_check.py` (new)

Helpers: build trace dicts with assistant messages containing tool_calls in OpenAI format:

```python
def _trace_with_tool_calls(*calls):
    """Build a trace with assistant tool calls.
    Each call is (name, args_dict).
    """
    tool_calls = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }
        for i, (name, args) in enumerate(calls)
    ]
    return [
        {"role": "user", "content": "do something"},
        {"role": "assistant", "tool_calls": tool_calls},
    ]
```

- **`test_tool_call_check_all_mode_pass`**: `expected_tools=[ToolCallSpec(tool_name="search")]`, trace has `search` call -> pass.
- **`test_tool_call_check_all_mode_fail`**: `expected_tools=[ToolCallSpec(tool_name="search"), ToolCallSpec(tool_name="fetch")]`, trace has only `search` -> fail.
- **`test_tool_call_check_any_mode_pass`**: `match_mode="any"`, `expected_tools=[ToolCallSpec(tool_name="search"), ToolCallSpec(tool_name="fetch")]`, trace has only `search` -> pass.
- **`test_tool_call_check_any_mode_fail`**: `match_mode="any"`, trace has neither expected tool -> fail.
- **`test_tool_call_check_ordered_pass`**: `match_mode="ordered"`, `expected_tools=[search, fetch]`, trace has `search` then `fetch` (possibly with others in between) -> pass.
- **`test_tool_call_check_ordered_fail`**: `match_mode="ordered"`, trace has `fetch` then `search` -> fail.
- **`test_tool_call_check_never_pass`**: `match_mode="never"`, `expected_tools=[ToolCallSpec(tool_name="delete")]`, trace has `search` but no `delete` -> pass.
- **`test_tool_call_check_never_fail`**: `match_mode="never"`, trace includes `delete` -> fail.
- **`test_tool_call_check_on_unexpected_fail`**: `on_unexpected_tools="fail"`, expected `search`, trace has `search` and `other` -> fail.
- **`test_tool_call_check_on_unexpected_ignore`**: `on_unexpected_tools="ignore"`, expected `search`, trace has `search` and `other` -> pass.
- **`test_tool_call_check_arg_match_exact`**: `expected_args={"query": ArgMatch(value="test")}`, actual args `{"query": "test"}` -> pass.
- **`test_tool_call_check_arg_match_contains`**: `ArgMatch(value="test", match_mode="contains")`, actual `"this is a test query"` -> pass.
- **`test_tool_call_check_arg_match_regex`**: `ArgMatch(value=r"\d+", match_mode="regex")`, actual `"item 42"` -> pass.
- **`test_tool_call_check_arg_match_fail`**: `expected_args={"query": ArgMatch(value="test")}`, actual `{"query": "other"}` -> fail.
- **`test_tool_call_check_missing_trace_skips`**: `trace=None` -> `({}, SkippedReason.missing_trace, ...)`.
- **`test_tool_call_check_empty_trace`**: `trace=[]` (no tool calls) with `match_mode="all"` -> fail (expected tool not found).
- **`test_tool_call_check_multiple_assistant_messages`**: Trace with multiple assistant messages, each with tool calls -> all calls are collected and evaluated.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_step_count_check.py` (new)

Helpers: build traces with varying numbers of user, assistant, and tool-call messages.

```python
def _multi_turn_trace(n_user=2, n_assistant=2, tools_per_assistant=0):
    """Build a trace with n_user user messages and n_assistant assistant messages."""
    trace = []
    for i in range(max(n_user, n_assistant)):
        if i < n_user:
            trace.append({"role": "user", "content": f"user msg {i}"})
        if i < n_assistant:
            msg = {"role": "assistant", "content": f"response {i}"}
            if tools_per_assistant > 0:
                msg["tool_calls"] = [
                    {"id": f"call_{i}_{j}", "type": "function", "function": {"name": f"tool_{j}", "arguments": "{}"}}
                    for j in range(tools_per_assistant)
                ]
            trace.append(msg)
    return trace
```

- **`test_step_count_tool_calls_pass`**: `count_type="tool_calls"`, `min_count=2`, `max_count=5`, trace with 3 tool calls -> pass.
- **`test_step_count_tool_calls_below_min`**: `min_count=5`, trace with 2 tool calls -> fail.
- **`test_step_count_tool_calls_above_max`**: `max_count=1`, trace with 3 tool calls -> fail.
- **`test_step_count_model_responses_pass`**: `count_type="model_responses"`, `min_count=1`, `max_count=3`, trace with 2 assistant messages with content -> pass.
- **`test_step_count_model_responses_no_content`**: Assistant message with no content (tool-call-only) is not counted as a model_response.
- **`test_step_count_turns_pass`**: `count_type="turns"`, `min_count=2`, trace with 2 user messages -> pass.
- **`test_step_count_turns_fail`**: `min_count=3`, trace with 2 user messages -> fail.
- **`test_step_count_min_only`**: Only `min_count` set (no max_count), count meets min -> pass.
- **`test_step_count_max_only`**: Only `max_count` set (no min_count), count under max -> pass.
- **`test_step_count_missing_trace_skips`**: `trace=None` -> `({}, SkippedReason.missing_trace, ...)`.
- **`test_step_count_empty_trace`**: `trace=[]` with `min_count=1` -> fail (count is 0).

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_dispatch_and_contract.py` (update existing)

Phase 2 left all V2 types unimplemented. Now that 6 are registered, update the dispatch tests:

- **Update `test_empty_map_raises`**: This test monkeypatched the map or relied on it being empty. Now that the map has entries, this test should either be removed or updated to test only for types NOT in the map (e.g., `V2EvalType.llm_judge`, `V2EvalType.code_eval`).
- **Add `test_dispatch_all_registered_types`**: Iterate over the 6 registered types, create a mock config with the corresponding properties class, call `v2_eval_adapter_from_config`, verify an instance of the correct adapter class is returned.
- **Add `test_dispatch_unregistered_types_raise`**: For `V2EvalType.llm_judge` and `V2EvalType.code_eval`, verify `NotImplementedError` is still raised.
- **Keep all other tests unchanged** (extraction helpers, base contract tests are unaffected).

### Test file: `libs/core/kiln_ai/adapters/eval/test_registry.py` (update existing)

- **Update `test_v2_dispatch_all_types_unimplemented`**: This test iterated over all `V2EvalType` values and expected all to raise. Now only `llm_judge` and `code_eval` should raise. Rename to `test_v2_dispatch_unimplemented_types` and test only those two.
- **Add `test_v2_dispatch_implemented_types`**: For each of the 6 registered types, verify the correct adapter class is returned.

## Out of Scope

- **llm_judge adapter** (Phase 4): Requires LLM invocation, prompt template rendering, thinking instructions, g_eval logprob weighting. Not a deterministic adapter.
- **code_eval adapter** (Phase 5): Requires sandboxed code execution via multiprocessing.
- **UI changes** (Phase 6): No frontend work in this phase.
- **Multi-turn trace execution**: Building conversation flows from `MultiTurnSyntheticEvalInputData`. The runner already skips multi-turn inputs with `SkippedReason.incompatible_input_shape`.
- **Deferred eval types**: `composite`, `threshold`, `json_schema`, `event_ordering`, `embedding_similarity`, `dag_metric` are not in V2EvalType and are future work.
- **EvalInput CRUD API**: Creating/listing/filtering EvalInputs via REST endpoints.
- **Trace-format standardization**: Adapters assume OpenAI `ChatCompletionMessageParam` dict format. No adapter-level format translation.
