# Unit 22-deterministic: Types: 6 deterministic/agent checks

Requirements: 68 total — MET 51, PARTIAL 7, MISSING 5, CONTRADICTED 1, DEFERRED_OK 1, CANNOT_VERIFY 3

---

## Extracted Requirements

### exact_match

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R01 | data-model | MET | — | ExactMatchProperties has `type: Literal["exact_match"]` | §3.1 schema | `eval.py:93-94` — `type: Literal[V2EvalType.exact_match] = V2EvalType.exact_match` | — |
| 22-R02 | data-model | MET | — | ExactMatchProperties has `value_expression: str \| None = None` | §3.1 schema | `eval.py:94` | — |
| 22-R03 | data-model | MET | — | ExactMatchProperties has `expected_value: str \| None = None` | §3.1 schema | `eval.py:95` | — |
| 22-R04 | data-model | MET | — | ExactMatchProperties has `reference_key: str \| None = None` | §3.1 schema | `eval.py:96` | — |
| 22-R05 | data-model | MET | — | ExactMatchProperties has `case_sensitive: bool = True` | §3.1 schema | `eval.py:97` | — |
| 22-R06 | data-model | MET | — | ExactMatchProperties XOR validator: exactly one of expected_value or reference_key | §3.1 schema `@model_validator` | `eval.py:99-105` — validator checks `(self.expected_value is None) == (self.reference_key is None)` | — |
| 22-R07 | behavior | MET | — | Extract value via extract(value_expression, ...) or whole final_message if None. Skip on null/Undefined. | §3.1 scorer step 1 | `v2_eval_exact_match.py:24-26` uses `extract_value` helper; `v2_eval_helpers.py:26-45` does exactly this | — |
| 22-R08 | behavior | MET | — | Resolve expected: expected_value literal OR reference_data[reference_key]. Skip on missing ref key. | §3.1 scorer step 2 | `v2_eval_exact_match.py:28-36` uses `check_reference_key` helper | — |
| 22-R09 | behavior | MET | — | Both values coerced to str for comparison. If case_sensitive=False, both lowercased. | §3.1 scorer step 3 | `v2_eval_exact_match.py:38-43` — `str(value)`, `str(expected)`, `.lower()` | — |
| 22-R10 | behavior | MET | — | Score: 1.0 (pass) or 0.0 (fail) | §3.1 scorer step 4-5 | `v2_eval_exact_match.py:45` — `build_binary_scores(self._output_scores, passed)` | — |

### pattern_match

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R11 | data-model | MET | — | PatternMatchProperties has type, value_expression, pattern, mode fields matching spec | §3.2 schema | `eval.py:108-113` — all fields match | — |
| 22-R12 | data-model | MET | — | mode: Literal["must_match", "must_not_match"] = "must_match" | §3.2 schema | `eval.py:112` | — |
| 22-R13 | data-model | MET | — | Save-time pattern validation via re.compile() in model_validator | §3.2 schema, §6 table | `eval.py:114-122` — `re.compile(self.pattern)` in `validate_pattern` | — |
| 22-R14 | behavior | MET | — | Uses re.search (not re.match) | §3.2 "Uses `re.search`..." | `v2_eval_pattern_match.py:32` — `re.search(props.pattern, actual)` | — |
| 22-R15 | behavior | MET | — | must_match: pass if match found; must_not_match: pass if no match | §3.2 scorer steps 4-5 | `v2_eval_pattern_match.py:40-43` | — |
| 22-R16 | behavior | MET | — | Coerce to str before matching | §3.2 scorer step 2 | `v2_eval_pattern_match.py:29` — `str(value)` | — |

### contains

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R17 | data-model | MET | — | ContainsProperties has type, value_expression, substring, reference_key, case_sensitive, mode matching spec | §3.3 schema | `eval.py:125-131` — all fields match | — |
| 22-R18 | data-model | MET | — | ContainsProperties XOR validator: exactly one of substring or reference_key | §3.3 schema | `eval.py:133-136` | — |
| 22-R19 | behavior | MET | — | must_contain mode: pass if substring found; must_not_contain: pass if not found | §3.3 scorer steps 4-5 | `v2_eval_contains.py:45-48` | — |
| 22-R20 | behavior | MET | — | Case insensitive: both lowercased | §3.3 scorer step 3 | `v2_eval_contains.py:40-43` | — |
| 22-R21 | data-model | MET | — | mode default: "must_contain" | §3.3 schema | `eval.py:131` | — |

### set_check

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R22 | data-model | MET | — | SetCheckProperties has type, value_expression, expected_set, reference_key, mode matching spec | §3.4 schema | `eval.py:140-145` — all fields match | — |
| 22-R23 | data-model | MET | — | SetCheckProperties XOR validator: exactly one of expected_set or reference_key | §3.4 schema | `eval.py:147-150` | — |
| 22-R24 | data-model | MET | — | mode default: "subset" | §3.4 schema | `eval.py:145` — `= "subset"` | — |
| 22-R25 | behavior | MET | — | Coerce extracted to set: list → set(str), str → JSON parse attempt → set, dict → keys | §3.4 scorer step 2 | `v2_eval_set_check.py:62-78` — `_coerce_to_set` covers all cases | — |
| 22-R26 | behavior | MET | — | subset: extracted_set <= expected_set | §3.4 scorer step 4 | `v2_eval_set_check.py:52-53` — `actual_set.issubset(expected_set)` | — |
| 22-R27 | behavior | MET | — | superset: extracted_set >= expected_set | §3.4 scorer step 4 | `v2_eval_set_check.py:54-55` — `actual_set.issuperset(expected_set)` | — |
| 22-R28 | behavior | MET | — | equal: extracted_set == expected_set | §3.4 scorer step 4 | `v2_eval_set_check.py:56-57` | — |

### tool_call_check

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R29 | data-model | MET | — | ArgMatch has value: JsonValue, match_mode: Literal["exact", "contains", "regex"] = "exact" | §3.5 schema | `eval.py:154-156` | — |
| 22-R30 | data-model | MET | — | ToolCallSpec has tool_name: str, expected_args: dict[str, ArgMatch] \| None = None | §3.5 schema | `eval.py:159-161` | — |
| 22-R31 | data-model | MET | — | ToolCallCheckProperties has expected_tools, match_mode, on_unexpected_tools matching spec | §3.5 schema | `eval.py:164-168` | — |
| 22-R32 | data-model | MET | — | match_mode default: "all" | §3.5 schema | `eval.py:167` | — |
| 22-R33 | data-model | MET | — | on_unexpected_tools default: "ignore" | §3.5 schema | `eval.py:168` | — |
| 22-R34 | behavior | MET | — | Skip with missing_trace if trace is None | §3.5 scorer step 1 | `v2_eval_tool_call_check.py:26-27` | — |
| 22-R35 | behavior | MET | — | Extract tool calls: iterate assistant messages, collect tool_calls with function name + parsed arguments | §3.5 scorer step 2, trace format | `v2_eval_tool_call_check.py:41-66` — parses `function.name` and `json.loads(arguments)` | — |
| 22-R36 | behavior | MET | — | match_mode "any": pass if at least one spec matched | §3.5 match_mode table | `v2_eval_tool_call_check.py:86-95` | — |
| 22-R37 | behavior | MET | — | match_mode "all": pass if every spec matched at least once | §3.5 match_mode table | `v2_eval_tool_call_check.py:96-106` | — |
| 22-R38 | behavior | MET | — | match_mode "ordered": all specs matched AND in listed order (cursor advancing through actual calls) | §3.5 match_mode table, scorer step 4 | `v2_eval_tool_call_check.py:107-108, 124-136` — `_check_ordered` uses advancing cursor | — |
| 22-R39 | behavior | MET | — | match_mode "never": pass if NO spec matched | §3.5 match_mode table | `v2_eval_tool_call_check.py:79-84` | — |
| 22-R40 | behavior | MET | — | on_unexpected_tools "fail": any unmatched actual call → fail | §3.5 on_unexpected_tools semantics | `v2_eval_tool_call_check.py:112-122` | — |
| 22-R41 | behavior | MET | — | Under match_mode="never", on_unexpected_tools is ignored | §3.5 "Under `match_mode="never"`, `on_unexpected_tools` is ignored" | `v2_eval_tool_call_check.py:79-84` — returns early before on_unexpected check | — |
| 22-R42 | behavior | MET | — | Per-arg exact: deep equality | §3.5 ArgMatch.match_mode table | `v2_eval_tool_call_check.py:156-157` — `actual == arg_match.value` | — |
| 22-R43 | behavior | MET | — | Per-arg contains: substring match on string representation | §3.5 ArgMatch.match_mode table | `v2_eval_tool_call_check.py:158-159` — `str(arg_match.value) in str(actual)` | — |
| 22-R44 | behavior | MET | — | Per-arg regex: re.search on string representation | §3.5 ArgMatch.match_mode table | `v2_eval_tool_call_check.py:160-163` — `re.search(str(arg_match.value), str(actual))` | — |
| 22-R45 | behavior | MET | — | When expected_args is None, only tool name matters | §3.5 "When `expected_args` is `None`...only the tool name matters" | `v2_eval_tool_call_check.py:143-144` — returns True after name match if `expected_args is None` | — |
| 22-R46 | validation | MISSING | minor | expected_tools must be non-empty list at save time | §6 table: "`expected_tools`: non-empty list" | `eval.py:164-168` — `expected_tools: list[ToolCallSpec]` has no `min_length=1` or validator enforcing non-empty | No save-time non-empty validation |
| 22-R47 | validation | MISSING | minor | ArgMatch regex values validated via re.compile at save time | §6 table: "If any `ArgMatch.match_mode="regex"`: `re.compile(str(value))`" | `eval.py:154-156` — ArgMatch has no model_validator for regex compilation | Missing save-time regex validation on ArgMatch |

### step_count_check

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R48 | data-model | MET | — | StepCountCheckProperties has type, count_type, min_count, max_count matching spec | §3.6 schema | `eval.py:171-175` | — |
| 22-R49 | data-model | MET | — | count_type: Literal["tool_calls", "model_responses", "turns"] | §3.6 schema | `eval.py:173` | — |
| 22-R50 | data-model | MET | — | min_count/max_count: int \| None = None | §3.6 schema | `eval.py:174-175` | — |
| 22-R51 | data-model | MET | — | Validator: at least one of min/max required | §3.6 schema check_bounds | `eval.py:178-181` | — |
| 22-R52 | data-model | MET | — | Validator: min <= max when both set | §3.6 schema check_bounds | `eval.py:182-188` | — |
| 22-R53 | behavior | MET | — | Skip with missing_trace if trace is None | §3.6 scorer step 1 | `v2_eval_step_count_check.py:28-32` | — |
| 22-R54 | behavior | MET | — | tool_calls: sum of len(msg.tool_calls) for assistant messages | §3.6 count_type table | `v2_eval_step_count_check.py:48-55` | — |
| 22-R55 | behavior | MET | — | model_responses: count of role=="assistant" messages | §3.6 count_type table | `v2_eval_step_count_check.py:56-60` | — |
| 22-R56 | behavior | MET | — | turns: count of role=="user" messages | §3.6 count_type table | `v2_eval_step_count_check.py:61-65` | — |
| 22-R57 | behavior | MET | — | Pass if count within bounds; fail otherwise | §3.6 scorer steps 3-5 | `v2_eval_step_count_check.py:37-42` | — |

### Shared infrastructure

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R58 | behavior | MET | — | Null/missing extraction → skip with extraction_failed | §1 value_expression semantics | `v2_eval_helpers.py:39-44` — returns `SkippedReason.extraction_failed` | — |
| 22-R59 | behavior | MET | — | Missing reference key → skip with missing_reference_key | §1 reference_key semantics | `v2_eval_helpers.py:56-75` — returns `SkippedReason.missing_reference_key` | — |
| 22-R60 | validation | MET | — | value_expression validated via compile_expression_or_raise at save time | §1 + §6 | `eval.py:716-727` — `validate_v2_templates_and_expressions` calls `compile_expression_or_raise` for the 4 extract-based types | — |
| 22-R61 | data-model | MET | — | tool_call_check and step_count_check bypass extract() entirely | §2 "do NOT use value_expression, extract(), or input_transform" | `v2_eval_tool_call_check.py` and `v2_eval_step_count_check.py` — neither imports or calls `extract_value` | — |
| 22-R62 | validation | MISSING | minor | reference_key save-time validation: non-empty string (min_length=1) | §1 "`reference_key`... Save-time validation: non-empty string (Pydantic `min_length=1`)" | `eval.py:96,129,144` — `reference_key: str \| None = None` with no `min_length` constraint | Empty-string reference_key can pass XOR validator but fail at runtime |

### Registration and adapter architecture

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R63 | architecture | MET | — | All 6 types registered in _V2_ADAPTER_MAP | §4 registration | `registry.py:25-34` — all 6 present | — |
| 22-R64 | architecture | MET | — | All 6 subclass BaseEval (via BaseV2EvalBridge) | §4 "Subclasses BaseEval (per C.11c)" | All 6 adapters subclass `BaseV2EvalBridge(BaseEval)` | — |
| 22-R65 | behavior | MET | — | build_binary_scores maps 0.0/1.0 across all declared score keys | §5 score output model | `v2_eval_helpers.py:13-23` — `{score.json_key(): value for score in output_scores}` | — |
| 22-R66 | data-model | DEFERRED_OK | — | Scalar-shorthand for expected_args deferred | §3.5 "Scalar-shorthand...deferred to implementation time" | Not implemented, which is the correct behavior for a deferred item | — |

### UI form layouts (components/70 §3.1)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R67 | UX | PARTIAL | minor | exact_match comparison source: "radio group" | 70 §3.1 "Comparison source — radio group" | `exact_match_form.svelte:35` — uses `select` dropdown instead of radio group | Select dropdown instead of radio group; functionally equivalent but different UX affordance |
| 22-R68 | UX | PARTIAL | minor | contains search string source: "radio group" | 70 §3.1 "Search string source — radio group" | `contains_form.svelte:42` — uses `select` dropdown instead of radio group | Same as above |
| 22-R69 | UX | PARTIAL | minor | set_check expected set source: "radio group" | 70 §3.1 "Expected set source — radio group" | `set_check_form.svelte:50` — uses `select` dropdown instead of radio group | Same as above |
| 22-R70 | UX | PARTIAL | minor | set_check expected set: "tag-input / multi-value field... Add items via enter or comma" | 70 §3.1 "If literal: tag-input / multi-value field for `expected_set`" | `set_check_form.svelte:67-73` — uses a textarea with one-per-line instead of tag input with enter/comma add | Textarea instead of tag-input; different interaction model |
| 22-R71 | UX | CONTRADICTED | minor | set_check form default mode should be "subset" (matching Pydantic default) | 22 §3.4 `mode: Literal["subset", "superset", "equal"] = "subset"` | `set_check_form.svelte:8` — `mode: "equal"` | Form default is "equal" but Pydantic model default is "subset". Editing an existing config is fine; creating a new one will show "equal" in the UI but saving without changing would produce a properties object with mode="equal", diverging from the spec's intended default. |
| 22-R72 | UX | MISSING | minor | tool_call_check: expected arguments in "optional collapsible section" collapsed by default | 70 §3.1 "Expected arguments — optional collapsible section" + §3.2 "arg-matching section is collapsed by default" | `tool_call_check_form.svelte:125-173` — args are always visible, no collapsible wrapper | Args section always visible, not collapsed |
| 22-R73 | UX | MISSING | minor | tool_call_check: on_unexpected_tools hidden when match_mode is "never" | 70 §3.1 "On unexpected tools — ... Hidden when match mode is 'Never.'" | `tool_call_check_form.svelte:98-108` — always visible regardless of match_mode | on_unexpected_tools select always visible; should be hidden when match_mode="never" |
| 22-R74 | UX | CANNOT_VERIFY | minor | Value expression fields include "?" help icon linking to Jinja2 expression docs or tooltip | 70 §3.2 "small '?' help icon linking to Jinja2 expression docs (or inline tooltip)" | Forms show `description` text on FormElement but no dedicated "?" icon/tooltip was found; may be handled by FormElement component generically | Would need to check FormElement rendering |
| 22-R75 | UX | CANNOT_VERIFY | minor | Radio groups disable inactive input to avoid confusion | 70 §3.2 "Radio groups for XOR fields... disable the inactive input" | Forms use select dropdowns (not radio groups) and conditionally render only the active input with `{#if}`, which is functionally equivalent to "disable the inactive input" (it's hidden entirely) | Different approach but achieves same goal; moot since select used instead of radio |
| 22-R76 | UX | PARTIAL | minor | Validation on blur and again on Save attempt | 70 §3.2 "All validation runs on blur (not on every keystroke) and again on Save attempt" | No `on:blur` handlers in any form. Server-side validation runs on save. No client-side blur validation. | Missing blur-time validation |
| 22-R77 | UX | PARTIAL | minor | step_count_check inline error for at-least-one-bound and min<=max | 70 §3.1 "Validation: at least one of min/max must be set; min <= max when both set. Shown as inline error." | `step_count_check_form.svelte:16-28` — `validate()` function exists but it is exported for external use, no inline error rendering in the component itself | Validation logic present but not shown as inline error |
| 22-R78 | UX | CANNOT_VERIFY | minor | Reference key fields include help text: "Key name in the eval input's reference data." | 70 §3.2 | Forms show `description` on FormElement for reference key fields but with different text ("The key in the reference data whose value...") — close enough to spec intent | — |

---

## Verifier-added requirements (source: verifier_added)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 22-R79 | behavior | MET | — | Empty trace (trace=[]) evaluated against bounds normally, not skipped | §3.6 "Empty trace (`trace=[]`): All counts are 0. Evaluated against bounds normally (not skipped)" | `v2_eval_step_count_check.py:28-32` — only skips if `trace is None`, not empty list; `_count` returns 0 for empty list | — |
| 22-R80 | behavior | MET | — | System messages not counted by any count_type | §3.6 "System messages: Not counted by any `count_type`" | `v2_eval_step_count_check.py:48-65` — only counts assistant/user roles, never system | — |
| 22-R81 | behavior | MET | — | Tool-role messages not counted directly | §3.6 "Tool-role messages: Not counted directly" | `v2_eval_step_count_check.py:48-65` — never counts tool role | — |
| 22-R82 | behavior | PARTIAL | minor | All six types produce binary 1.0/0.0 scores only (no partial scores) | §5 "No partial scores... all-or-nothing" | All adapters use `build_binary_scores` which produces only 1.0 or 0.0. MET in adapters. However, `build_binary_scores` returns `{}` when `output_scores` is empty, which technically is not 1.0/0.0, but that edge case is guarded by Eval-level validation requiring at least one output_score. | — |
