---
status: complete
approved: true
alignment_refs: [A2.4, D.3, J.37, J.38]
opens: []
summary: exact_match, pattern_match, set_check, contains, tool_call_check, step_count_check — grouped because they share extraction infrastructure.
---

# Type: Deterministic Basics

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 gap-fill
**Status:** complete

## TL;DR

- Six deterministic V2 EvalConfigTypes: `exact_match`, `pattern_match`, `set_check`, `contains`, `tool_call_check`, `step_count_check`. No LLM call. No sandbox. Pure comparison/inspection logic.
- Four types (`exact_match`, `pattern_match`, `set_check`, `contains`) share the `extract()` / `value_expression` infrastructure from `components/40`. Two types (`tool_call_check`, `step_count_check`) are **typed exceptions** that walk the trace internally and bypass `extract()` entirely.
- `tool_call_check` properties expanded per J.37: `expected_tools: list[ToolCallSpec]`, `match_mode` (any/all/ordered/never), per-arg `ArgMatch` with per-arg `match_mode` (exact/contains/regex), `on_unexpected_tools` (ignore/fail).
- `step_count_check` added per J.38: `count_type` (tool_calls/model_responses/turns), `min_count`/`max_count` bounds with at-least-one-required validator.
- All six subclass `BaseEval` directly (per C.11c). All six register in the `_V2_ADAPTER_MAP` in `components/20`'s two-level dispatch. All produce scores conforming to the parent `Eval.output_scores` shape.

---

## 1. Shared infrastructure: `extract()` and `value_expression` (D.3)

Four of the six types (`exact_match`, `pattern_match`, `set_check`, `contains`) use the shared `extract()` helper from the general Kiln infrastructure (`components/06_prereq_input_transform.md`, exported from `libs/core`). Their properties carry a `value_expression: str | None` field — a Jinja2 expression evaluated via `extract()` against the `EvalTaskInput` dict assembled by the eval runner per `components/40` section 2.

**`value_expression` semantics (from `components/40` section 3.2):**

- Jinja2 expression evaluated via `extract(expr, eval_task_input.model_dump())`.
- Returns whatever the expression yields (string, dict, list, int).
- If `None` (field omitted): extracted value is the whole `final_message`.
- Save-time validation: `compile_expression_or_raise(value_expression)` from prereq infra.
- Null/missing extraction result: case skipped with `skipped_reason: extraction_failed` + `skipped_detail: "<value_expression>"` per C.runner.1. See `components/85` section 2.2 for the canonical `SkippedReason` enum.

**`reference_key` semantics (shared across `exact_match`, `set_check`, `contains`):**

- String naming a key in `EvalInput.reference` (the flat `dict[str, JsonValue]` per A1.2).
- At eval time: `expected = eval_task_input["reference_data"][reference_key]`.
- If the reference key is missing or `reference_data` is None: case skipped with `skipped_reason: missing_reference_key` + `skipped_detail: "<key>"` per C.runner.1. See `components/85` section 2.2 for the canonical `SkippedReason` enum.
- Save-time validation: non-empty string (Pydantic `min_length=1`).

**Source extraction flow (four extract-based types):**

```
EvalInput + TaskRun
      |
      v
eval runner assembles EvalTaskInput
      |
      v
extract(value_expression, eval_task_input.model_dump())
      |
      v
extracted_value  -->  type-specific comparison logic  -->  pass/fail score
```

---

## 2. Typed exceptions: `tool_call_check` and `step_count_check`

These two types do NOT use `value_expression`, `extract()`, or `input_transform`. They are **typed deterministic trace inspectors** that walk the trace JSON (`EvalTaskInput.trace`, which is `list[ChatCompletionMessageParam]` in OpenAI format per `components/40` section 2) internally with typed matchers. This is consistent with `components/40` sections 3.3 and 3.3b.

**Why the exception:** These types operate on structural properties of the trace (tool call sequences, step counts) rather than extracting a single value from the output. The trace is a list of messages with roles and tool-call structures — walking it requires typed iteration, not a Jinja2 expression that returns a scalar.

**Source extraction flow (two trace-walker types):**

```
EvalInput + TaskRun
      |
      v
eval runner assembles EvalTaskInput
      |
      v
adapter reads eval_task_input.trace directly (no extract())
      |
      v
typed trace walker  -->  pass/fail score
```

**Trace availability requirement:** Both types require `trace` to be non-None on `EvalTaskInput`. If `trace` is None (e.g. final-answer-only eval run), the case is skipped with `skipped_reason: missing_trace` (a canonical `SkippedReason` enum value; see `components/85` section 2.2). This is not controlled by `value_expression` / `required_var` (those are extraction-layer concepts); it is a type-level precondition checked by the adapter before walking.

---

## 3. Per-type design

### 3.1 `exact_match`

**Purpose:** String/enum equality check — compare an extracted value against a literal or a reference data value.

**Properties schema:**

```python
class ExactMatchProperties(BaseModel):
    type: Literal["exact_match"] = "exact_match"
    value_expression: str | None = None       # Jinja2 expr; None = whole final_message
    expected_value: str | None = None         # literal to compare against
    reference_key: str | None = None          # OR pull from reference_data[reference_key]
    case_sensitive: bool = True               # string comparison mode

    @model_validator(mode="after")
    def validate_comparison_source(self):
        if (self.expected_value is None) == (self.reference_key is None):
            raise ValueError(
                "Exactly one of expected_value or reference_key must be set"
            )
        return self
```

**Scorer behavior:**

1. Extract value via `extract(value_expression, ...)` (or whole `final_message` if None). Skip on null/Undefined.
2. Resolve expected: `expected_value` (literal) or `reference_data[reference_key]` (from EvalInput.reference). Skip on missing reference key.
3. Both values coerced to `str` for comparison. If `case_sensitive=False`, both lowercased.
4. **Pass:** `str(extracted) == str(expected)` (after optional case folding). Score: `1.0`.
5. **Fail:** mismatch. Score: `0.0`.

**Score output:** Single score per `Eval.output_scores` entry. Value is `1.0` (pass) or `0.0` (fail). The score key is determined by the parent `Eval.output_scores` shape (per C.9).

---

### 3.2 `pattern_match`

**Purpose:** Regex check on extracted value — verify output matches (or does not match) a regular expression.

**Properties schema:**

```python
class PatternMatchProperties(BaseModel):
    type: Literal["pattern_match"] = "pattern_match"
    value_expression: str | None = None       # Jinja2 expr; None = whole final_message
    pattern: str                              # Python regex (re module syntax)
    mode: Literal["must_match", "must_not_match"] = "must_match"

    @model_validator(mode="after")
    def validate_pattern(self):
        import re
        try:
            re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        return self
```

**Scorer behavior:**

1. Extract value via `extract()`. Skip on null/Undefined.
2. Coerce to `str`.
3. Run `re.search(pattern, extracted_str)`.
4. **`must_match` mode:** Pass if match found. Fail otherwise.
5. **`must_not_match` mode:** Pass if no match. Fail if match found.
6. Score: `1.0` (pass) or `0.0` (fail).

**Implementation note:** Uses `re.search` (not `re.match`) — pattern can match anywhere in the string. Users wanting full-string match use `^...$` anchors. This matches Promptfoo's regex assertion behavior.

**Save-time validation:** Pattern compiled via `re.compile()` in the `model_validator`. Invalid regex rejects the save.

---

### 3.3 `contains`

**Purpose:** Substring presence or absence check — verify output contains (or does not contain) a given substring.

**Properties schema:**

```python
class ContainsProperties(BaseModel):
    type: Literal["contains"] = "contains"
    value_expression: str | None = None       # Jinja2 expr; None = whole final_message
    substring: str | None = None              # literal substring to search for
    reference_key: str | None = None          # OR pull substring from reference_data
    case_sensitive: bool = True
    mode: Literal["must_contain", "must_not_contain"] = "must_contain"

    @model_validator(mode="after")
    def validate_comparison_source(self):
        if (self.substring is None) == (self.reference_key is None):
            raise ValueError(
                "Exactly one of substring or reference_key must be set"
            )
        return self
```

**Scorer behavior:**

1. Extract value via `extract()`. Skip on null/Undefined.
2. Resolve search string: `substring` (literal) or `reference_data[reference_key]`. Skip on missing reference key.
3. Both coerced to `str`. If `case_sensitive=False`, both lowercased.
4. **`must_contain` mode:** Pass if search string is found in extracted value.
5. **`must_not_contain` mode:** Pass if search string is NOT found.
6. Score: `1.0` (pass) or `0.0` (fail).

**Design note:** `mode` added to `contains` for symmetry with `pattern_match`. This avoids needing a separate `not_contains` type and covers the common "output must NOT mention X" use case.

---

### 3.4 `set_check`

**Purpose:** Set containment check — compare extracted set against a reference set using subset, superset, or equality semantics.

**Properties schema:**

```python
class SetCheckProperties(BaseModel):
    type: Literal["set_check"] = "set_check"
    value_expression: str | None = None       # Jinja2 expr; None = whole final_message
    expected_set: list[str] | None = None     # literal set to compare against
    reference_key: str | None = None          # OR pull from reference_data
    mode: Literal["subset", "superset", "equal"] = "subset"

    @model_validator(mode="after")
    def validate_comparison_source(self):
        if (self.expected_set is None) == (self.reference_key is None):
            raise ValueError(
                "Exactly one of expected_set or reference_key must be set"
            )
        return self
```

**Scorer behavior:**

1. Extract value via `extract()`. Skip on null/Undefined.
2. Coerce extracted value to a set of strings:
   - If `list`: `set(str(item) for item in extracted)`
   - If `str`: attempt JSON parse; if list, convert to set; otherwise `{extracted_str}` (single-element set)
   - If `dict`: `set(extracted.keys())`
3. Resolve expected set: `expected_set` (literal list) or `reference_data[reference_key]` (must be a list). Convert to `set(str(item) for item in ...)`. Skip on missing reference key.
4. Comparison:
   - **`subset`:** Pass if `extracted_set <= expected_set` (extracted is a subset of expected).
   - **`superset`:** Pass if `extracted_set >= expected_set` (extracted is a superset of expected).
   - **`equal`:** Pass if `extracted_set == expected_set` (exact set equality).
5. Score: `1.0` (pass) or `0.0` (fail).

**Semantics clarification:** `mode="subset"` means "the extracted values must all be members of the expected set" — this is the natural default for "did the model return valid categories from a known set." `mode="superset"` means "the extracted values must include everything in the expected set" — useful for "did the model mention all required items."

---

### 3.5 `tool_call_check` (J.37)

**Purpose:** Tool trajectory check — verify that an agent called the right tools, in the right order, with the right arguments. Covers existence, ordering, forbidden-tool (blocklist), and per-argument matching. This is a typed exception that walks the trace internally (no `extract()` / `value_expression`).

**Properties schema (locked shape from reference/ALIGNMENT.md J.37):**

```python
class ArgMatch(BaseModel):
    """Per-argument matching specification."""
    value: JsonValue                           # expected argument value
    match_mode: Literal["exact", "contains", "regex"] = "exact"


class ToolCallSpec(BaseModel):
    """Specification for one expected (or forbidden) tool call."""
    tool_name: str
    expected_args: dict[str, ArgMatch] | None = None   # None = ignore args


class ToolCallCheckProperties(BaseModel):
    type: Literal["tool_call_check"] = "tool_call_check"
    expected_tools: list[ToolCallSpec]
    match_mode: Literal["any", "all", "ordered", "never"] = "all"
    on_unexpected_tools: Literal["ignore", "fail"] = "ignore"
```

**`match_mode` semantics:**

| Mode | Meaning | Pass condition |
|---|---|---|
| `any` | At least one expected tool was called (subset match) | Any `ToolCallSpec` in `expected_tools` has a matching call in the trace |
| `all` (default) | Every expected tool was called at least once, in any order | All `ToolCallSpec`s have at least one matching call |
| `ordered` | Expected tools appear in the listed sequence | All `ToolCallSpec`s matched AND in the listed order (other calls between them are OK unless `on_unexpected_tools="fail"`) |
| `never` | Fail if any expected tool was called | None of the `expected_tools` has a matching call in the trace. Under this mode `expected_tools` reads as "forbidden tools" |

**`on_unexpected_tools` semantics:**

- `ignore` (default): Tool calls not listed in `expected_tools` are ignored.
- `fail`: Any tool call not matching an entry in `expected_tools` causes the check to fail. Strict allowlist mode — "the agent must call ONLY these tools."
- Under `match_mode="never"`, `on_unexpected_tools` is ignored (every tool is unexpected relative to a forbidden list).

**Per-arg matching (`ArgMatch.match_mode`):**

| Mode | Behavior |
|---|---|
| `exact` (default) | `actual_arg_value == expected.value` (deep equality for dicts/lists, value equality for scalars) |
| `contains` | `str(expected.value) in str(actual_arg_value)` — substring match on string representation |
| `regex` | `re.search(str(expected.value), str(actual_arg_value))` — regex match on string representation |

When `expected_args` is `None` on a `ToolCallSpec`, argument values are ignored — only the tool name matters for matching.

**Scorer behavior:**

1. Read `eval_task_input.trace`. Skip with `skipped_reason: missing_trace` if None (canonical `SkippedReason` value; `components/85` section 2.2).
2. Extract all tool calls from the trace: iterate assistant-role messages, collect each `tool_calls[*]` entry (function name + arguments dict). This produces an ordered list of `(tool_name, args_dict)` tuples representing the actual trace.
3. For each `ToolCallSpec` in `expected_tools`, find matching actual calls:
   - Name match: `actual.tool_name == spec.tool_name`.
   - Arg match (if `spec.expected_args` is not None): for each `(arg_name, arg_match)` in `spec.expected_args`, verify the actual call's arguments contain `arg_name` and the value satisfies `arg_match.match_mode`.
4. Apply `match_mode`:
   - `any`: pass if at least one spec matched.
   - `all`: pass if every spec matched at least once.
   - `ordered`: pass if every spec matched AND matches appear in `expected_tools` order (using a cursor that advances through actual calls; non-matching calls between matches are allowed unless `on_unexpected_tools="fail"`).
   - `never`: pass if NO spec matched.
5. If `on_unexpected_tools="fail"` (and `match_mode != "never"`): check that every actual tool call matched at least one `ToolCallSpec`. If any unmatched actual call exists, fail.
6. Score: `1.0` (pass) or `0.0` (fail).

**Trace format assumption (verified 2026-06-02):** Trace is OpenAI-format `list[ChatCompletionMessageParam]`. Assistant messages may carry `tool_calls: list[{id, type, function: {name, arguments}}]`. The `arguments` field is a JSON string (per OpenAI spec); the adapter parses it to a dict before arg matching.

**Scalar-shorthand for `expected_args` (deferred):** J.37 notes that a scalar-shorthand union for `expected_args` values (`JsonValue | ArgMatch`, where a bare scalar means `ArgMatch(value=scalar, match_mode="exact")`) is deferred to implementation time as an ergonomics nicety. The locked shape above (always `ArgMatch`) is canonical. If implemented, the shorthand is a deserialization convenience backed by a Pydantic validator that normalizes bare scalars to `ArgMatch` instances.

**Use case examples (from J.37):**

```yaml
# "Agent must call search_web at least once"
type: tool_call_check
expected_tools: [{tool_name: search_web}]
match_mode: any

# "Agent must call search_web THEN fetch_page in order"
type: tool_call_check
expected_tools:
  - {tool_name: search_web}
  - {tool_name: fetch_page}
match_mode: ordered

# "Agent must call search_web with query containing 'Kiln'"
type: tool_call_check
expected_tools:
  - tool_name: search_web
    expected_args:
      query: {value: "Kiln", match_mode: contains}

# "Agent must call ONLY search_web and fetch_page (no other tools)"
type: tool_call_check
expected_tools:
  - {tool_name: search_web}
  - {tool_name: fetch_page}
match_mode: all
on_unexpected_tools: fail

# "Agent must NEVER call delete_database"
type: tool_call_check
expected_tools: [{tool_name: delete_database}]
match_mode: never
```

**Competitive coverage:** Covers Promptfoo's `trajectory:tool-used` (existence), `trajectory:tool-sequence` (ordering), `trajectory:tool-args-match` (arg matching) — three of five trajectory assertion types — plus forbidden-tool checking that Promptfoo lacks.

---

### 3.6 `step_count_check` (J.38)

**Purpose:** Agent efficiency check — count tool calls, model responses, or turns in the trace and verify the count falls within bounds. This is a typed exception that walks the trace internally (no `extract()` / `value_expression`).

**Properties schema (locked shape from reference/ALIGNMENT.md J.38):**

```python
class StepCountCheckProperties(BaseModel):
    type: Literal["step_count_check"] = "step_count_check"
    count_type: Literal["tool_calls", "model_responses", "turns"]
    min_count: int | None = None
    max_count: int | None = None

    @model_validator(mode="after")
    def check_bounds(self):
        if self.min_count is None and self.max_count is None:
            raise ValueError(
                "step_count_check requires at least one of min_count / max_count"
            )
        if (self.min_count is not None and self.max_count is not None
                and self.min_count > self.max_count):
            raise ValueError("min_count must be <= max_count")
        return self
```

**`count_type` semantics (verified against actual Kiln trace shape 2026-06-02):**

Trace is `list[ChatCompletionMessageParam]` on `TaskRun.trace`; roles are system / user / assistant / tool.

| `count_type` | What it counts | Counting rule |
|---|---|---|
| `tool_calls` | Individual tool-call requests across assistant messages | For each assistant-role message with `tool_calls`, add `len(tool_calls)`. An assistant message requesting 3 tool calls contributes 3. |
| `model_responses` | Assistant-role entries in the trace | Count messages where `role == "assistant"`. One per LLM response; an assistant message requesting N tool calls counts as **1**. |
| `turns` | User-role entries in the trace | Count messages where `role == "user"`. One per user-to-assistant exchange. Single-turn evals always count as **1**. |

**`model_responses` and `turns` do not collapse:** A single-turn run with 2 sequential tool calls has `model_responses=3`, `turns=1`, `tool_calls=2`. They coincide only in the degenerate no-tools, single-turn case.

**Scorer behavior:**

1. Read `eval_task_input.trace`. Skip with `skipped_reason: missing_trace` if None (canonical `SkippedReason` value; `components/85` section 2.2).
2. Walk the trace and count based on `count_type`:
   - `tool_calls`: sum of `len(msg.tool_calls)` for each assistant-role message that has `tool_calls`.
   - `model_responses`: count of messages with `role == "assistant"`.
   - `turns`: count of messages with `role == "user"`.
3. Check bounds:
   - If `min_count` is set: `count >= min_count` required.
   - If `max_count` is set: `count <= max_count` required.
4. **Pass:** count within bounds. Score: `1.0`.
5. **Fail:** count outside bounds. Score: `0.0`.

**Edge cases:**

- **Single-turn + `count_type="turns"`:** Valid, counts 1. `max_count=1` passes trivially (correct answer for "must be one-shot"). Not skipped.
- **Empty trace (`trace=[]`):** All counts are 0. Evaluated against bounds normally (not skipped — an empty trace is a valid trace, just with zero steps).
- **System messages:** Not counted by any `count_type`. System-role messages are preamble, not steps.
- **Tool-role messages:** Not counted directly. Tool-role messages are tool *responses* (from the tool back to the model), not tool *calls*. The call count comes from assistant messages' `tool_calls` field.

**`tokens` count_type — out of scope for V2.0:** Token count is cost-evaluation territory, conceptually distinct from step efficiency. Additive later if users ask — adding a new literal to `count_type` is non-breaking. Not foreclosed.

**Use case examples (from J.38):**

```yaml
# "Agent should solve in <= 10 tool calls"
type: step_count_check
count_type: tool_calls
max_count: 10

# "Agent should take at least 2 user turns (rules out one-shot)"
type: step_count_check
count_type: turns
min_count: 2

# "Agent should make 3-7 model calls (efficiency band)"
type: step_count_check
count_type: model_responses
min_count: 3
max_count: 7
```

**Competitive coverage:** Covers Promptfoo's `trajectory:step-count` assertion type.

---

## 4. Adapter architecture

All six deterministic types follow the same adapter pattern:

```python
class ExactMatchAdapter(BaseEval):
    """V2 adapter for exact_match. Subclasses BaseEval (per C.11c)."""

    async def run_eval(
        self, item, **kwargs
    ) -> tuple[EvalScores, dict[str, str] | None]:
        # Signature matches the abstract adapter contract in components/45 section 5.3
        # (returns (scores, intermediate_outputs); deterministic types have no
        # intermediate_outputs, so the second element is always None).
        # 1. Extract value
        props = self.eval_config.properties  # typed: ExactMatchProperties
        eval_task_input = self._build_eval_task_input(item)  # components/45 section 6.3
        extracted = extract(props.value_expression, eval_task_input) \
                    if props.value_expression else eval_task_input.get("final_message")
        if extracted is None:
            raise SkipCaseError(SkippedReason.extraction_failed, detail=props.value_expression)

        # 2. Resolve expected
        if props.reference_key:
            ref_data = eval_task_input.get("reference_data") or {}
            expected = ref_data.get(props.reference_key)
            if expected is None:
                raise SkipCaseError(SkippedReason.missing_reference_key, detail=props.reference_key)
        else:
            expected = props.expected_value

        # 3. Compare
        a, b = str(extracted), str(expected)
        if not props.case_sensitive:
            a, b = a.lower(), b.lower()
        passed = (a == b)

        # 4. Score
        return self.build_scores(1.0 if passed else 0.0), None
```

**Adapter conventions:**

- `self.eval_config.properties` is the typed properties instance (Pydantic discriminated union, per A2.1/A2.8). No casting needed — the registry guarantees the correct type.
- Skips use `raise SkipCaseError(SkippedReason.X, detail=...)` — the same adapter-level mechanism as `components/21` (the runner catches it and persists a skipped EvalRun per C.runner.1 / E.18; exact exception type is a `components/45` detail).
- `self.build_scores(value)` constructs scores conforming to `Eval.output_scores`. For deterministic types producing a single pass/fail, this maps the 0.0/1.0 value across all declared score keys (per C.9 — each EvalConfig must produce all of `Eval.output_scores`).
- No LLM call. No model fields. No `scoring_utils.py` consumption. These adapters are pure logic.

**Registration (per `components/20` section 2.2):**

```python
_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseEval]] = {
    # ... other types ...
    V2EvalType.exact_match: ExactMatchAdapter,
    V2EvalType.pattern_match: PatternMatchAdapter,
    V2EvalType.set_check: SetCheckAdapter,
    V2EvalType.contains: ContainsAdapter,
    V2EvalType.tool_call_check: ToolCallCheckAdapter,
    V2EvalType.step_count_check: StepCountCheckAdapter,
}
```

---

## 5. Score output model

All six types produce **binary pass/fail scores**: `1.0` (pass) or `0.0` (fail). This is a deliberate constraint — deterministic checks are boolean assertions, not graded rubrics.

**Mapping to `Eval.output_scores`:** Per C.9, each EvalConfig must produce all score keys declared by the parent Eval's `output_scores: list[EvalOutputScore]`. For deterministic types:

- If the Eval declares a single output score (common case): the pass/fail value maps directly.
- If the Eval declares multiple output scores (calibration scenario where the deterministic check is a candidate alongside an LLM judge): the deterministic adapter writes the same 0.0/1.0 value to every declared score key. This is semantically correct — a deterministic check either passes or fails as a whole; per-dimension grading is the judge's job.

**No partial scores.** Unlike `llm_judge` (which can produce per-criterion graded scores), deterministic types are all-or-nothing. This simplicity is a feature — the user knows exactly what "pass" means.

---

## 6. Save-time validation summary

| Type | Validated at save time |
|---|---|
| `exact_match` | `value_expression`: `compile_expression_or_raise()`. Exactly one of `expected_value`/`reference_key`. |
| `pattern_match` | `value_expression`: `compile_expression_or_raise()`. `pattern`: `re.compile()`. |
| `contains` | `value_expression`: `compile_expression_or_raise()`. Exactly one of `substring`/`reference_key`. |
| `set_check` | `value_expression`: `compile_expression_or_raise()`. Exactly one of `expected_set`/`reference_key`. |
| `tool_call_check` | `expected_tools`: non-empty list. Per-arg `ArgMatch.value`: present. If any `ArgMatch.match_mode="regex"`: `re.compile(str(value))`. |
| `step_count_check` | At least one of `min_count`/`max_count` set. `min_count <= max_count` when both set. |

Jinja2 expression validation (on `value_expression`) uses `compile_expression_or_raise()` from the general infra prereq (`components/06`). Regex validation uses Python `re.compile()`. Mutual-exclusivity constraints use Pydantic `model_validator(mode="after")`.

---

## 7. Implementation budget

| Type | Schema LOC (est.) | Adapter LOC (est.) | Phase |
|---|---|---|---|
| `exact_match` | ~15 | ~25 | Phase 1 |
| `pattern_match` | ~15 | ~20 | Phase 1 |
| `contains` | ~15 | ~25 | Phase 1 |
| `set_check` | ~20 | ~30 | Phase 1 |
| `tool_call_check` | ~25 | ~120 | Phase 1 |
| `step_count_check` | ~20 | ~50 | Phase 1 |
| **Total** | **~110** | **~270** | — |

All six are Phase 1 (must-ship EvalConfigTypes per A2.4). The four simple types are trivial; `tool_call_check` carries the most logic (ordering + arg matching); `step_count_check` is a straightforward trace walker.

---

## 8. Alignment reference coverage

| Ref | Decision | Coverage in this file |
|---|---|---|
| A2.4 | V2.0 lean catalog — 7 must-ship types | Section 1 (shared infra), sections 3.1-3.6 (all six deterministic types), section 7 (Phase 1 implementation) |
| D.3 | Eval consumer design — `extract()` for simple-check types; typed exceptions for trace walkers | Section 1 (`value_expression` / `extract()` semantics), section 2 (typed exceptions bypass), section 4 (adapter pattern) |
| J.37 | `tool_call_check` properties expansion | Section 3.5 (full locked schema, match_mode semantics, per-arg ArgMatch, on_unexpected_tools, scorer behavior, use cases) |
| J.38 | `step_count_check` — new EvalConfigType | Section 3.6 (full locked schema, count_type semantics, bounds validator, scorer behavior, edge cases, use cases) |

---

## Opens

None. All four alignment_refs are fully covered. No blocking questions remain for this file.
