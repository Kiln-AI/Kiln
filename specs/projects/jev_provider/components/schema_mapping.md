---
status: draft
---

# Component: Schema Mapping (`adapters/jev/jev_schema_mapping.py`)

## Purpose and Scope

Pure functions, no I/O:

1. Turn a Kiln task output JSON schema into a dict of Jev questions, or fail with one aggregated, user-readable error.
2. Turn Jev answers back into a JSON object matching the schema, plus a probability distribution per property keyed by output value.

Not in scope: building the `state`, HTTP, validation of the final output against the schema (the base adapter does that).

## Public Interface

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any

class JevIncompatibleSchemaError(ValueError):
    """Raised when one or more properties cannot be mapped. Message lists every property."""

class MappedKind(str, Enum):
    string_choice = "string_choice"
    integer_choice = "integer_choice"
    noul = "noul"
    score = "score"

@dataclass(frozen=True)
class MappedQuestion:
    key: str
    kind: MappedKind
    question: JevQuestion               # NoulQuestion | ChoiceQuestion | ScoreQuestion (wire models from jev_client)
    enum_values: tuple[str | int, ...] | None = None   # choice kinds: original values, schema order
    minimum: int | None = None                          # score kind: integer offset for level 0

def questions_from_output_schema(schema: dict[str, Any]) -> dict[str, MappedQuestion]:
    """Map every property of an object schema. Raises JevIncompatibleSchemaError with all failures."""

def output_from_answers(
    mappings: dict[str, MappedQuestion],
    answers: dict[str, JevAnswer],
) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    """Decode answers into (output_json, probabilities_by_property). Raises RuntimeError on a
    missing answer or an answer whose type doesn't match the question."""

def question_instructions(prop: dict[str, Any]) -> str | None:
    """description, else title, else None."""
```

`ERROR_PREFIX = "Jev (TypeSafe AI) can't run this task:"` lives in this module and is imported by the adapter so every compatibility error shares the prefix.

## Mapping algorithm (`questions_from_output_schema`)

```
properties = schema.get("properties") or {}
if not properties: raise JevIncompatibleSchemaError(f"{ERROR_PREFIX} the output schema has no properties.")
mappings, failures = {}, []
for key, prop in properties.items():        # dict order == schema order
    try: mappings[key] = _map_property(key, prop)
    except _PropertyUnsupported as e: failures.append(f"- {key}: {e}")
if failures: raise JevIncompatibleSchemaError(
    f"{ERROR_PREFIX} the output schema has properties Jev can't answer:\n" + "\n".join(failures)
    + "\nSupported property shapes: a string enum, an integer enum, a boolean, or an integer with minimum and maximum spanning 2 to 10 values.")
return mappings
```

`_map_property(key, prop)` decision order (first match wins; `_PropertyUnsupported` is a private exception with the reason text):

1. Any of `anyOf`, `oneOf`, `allOf`, `$ref`, `const` present → unsupported: "uses <keyword>, which Jev can't answer".
2. `enum` present:
   - Empty list → "enum has no values".
   - All values `str` and `type` in (absent, `"string"`) → `string_choice`. Criteria `{value: None}` in order. Duplicate values (after `str()`) → "enum has duplicate values".
   - All values `int` (and not `bool`) and `type` in (absent, `"integer"`) → `integer_choice`. Criteria `{str(value): None}`. Duplicates → same error.
   - Otherwise → "enum values must be all strings or all integers, and match the declared type".
3. `type == "boolean"` → `noul`. Criteria omitted. Instructions per `question_instructions`.
4. `type == "integer"`:
   - `minimum` and `maximum` both present and both ints (accept a float with `.is_integer()`, coerce) → levels = `maximum - minimum + 1`.
   - Missing either bound, or bounds not integral → "integer needs both minimum and maximum (exclusive bounds are not supported)".
   - `levels < 2` → "integer range must span at least 2 values"; `levels > 10` → "integer range spans N values, Jev supports at most 10".
   - Else → `score` with `criteria=[str(v) for v in range(minimum, maximum + 1)]`, `minimum` stored.
5. `type` is a list → "multiple types are not supported".
6. Anything else (`string` without enum, `number`, `array`, `object`, `null`, missing type) → "type <t> is not supported" (or "no type or enum").

`question_instructions`: `prop.get("description")` if a non-empty string, else `prop.get("title")` if non-empty, else `None`. Whitespace is preserved; Kiln's eval descriptions contain newlines and that is fine because Jev accepts any string.

Note on `bool` vs `int`: in Python `True` is an `int`. Check `isinstance(v, bool)` first and treat booleans inside an `enum` as unsupported.

## Decoding algorithm (`output_from_answers`)

For each `key, mapping` in `mappings` (schema order):

- `answer = answers.get(key)`; missing → `RuntimeError(f"TypeSafe AI returned an unexpected response: no answer for '{key}'")`.
- Type check: `noul` kind needs `NoulAnswer`, choice kinds need `ChoiceAnswer`, score needs `ScoreAnswer`; mismatch → `RuntimeError(... "answer for '{key}' has type {answer.type}, expected {expected}")`.

Per kind:

| kind | output value | probabilities (keys are strings) |
|---|---|---|
| `string_choice` | `answer.choice` (must be in `enum_values`, else `RuntimeError`) | `{label: p for label, p in answer.probabilities.items()}` |
| `integer_choice` | `int(answer.choice)` | same, labels are already `str(int)` |
| `noul` | `answer.noul >= 0.5` | `{"true": p, "false": 1.0 - p}` |
| `score` | `minimum + argmax_level` where `argmax_level = min(level for level with max probability)` over `answer.probabilities` keys parsed as `int`; if `probabilities` is empty fall back to `minimum + round(answer.score)` clamped to the range | `{str(minimum + level): p for level, p in answer.probabilities.items()}` |

Return `(output, probabilities)`. Probabilities are not rounded here; the adapter rounds only the persisted copy.

## Dependencies

- Imports wire models from `jev_client.py` (`NoulQuestion`, `ChoiceQuestion`, `ScoreQuestion`, `NoulAnswer`, `ChoiceAnswer`, `ScoreAnswer`).
- Used by `JevAdapter`.

## Test Plan (`test_jev_schema_mapping.py`)

Mapping, one test per row unless noted (parametrize where natural):

- `test_string_enum_maps_to_choice`: `{"type":"string","enum":["pass","fail"]}` → choice, criteria order and `None` descriptions, instructions from description.
- `test_string_enum_without_type`: no `type` key still maps to choice.
- `test_integer_enum_maps_to_choice_with_string_labels`: `{"enum":[1,2,3]}`.
- `test_enum_bool_values_rejected`, `test_enum_mixed_values_rejected`, `test_enum_empty_rejected`, `test_enum_duplicate_rejected`, `test_enum_type_mismatch_rejected` (`type: integer` with string values).
- `test_boolean_maps_to_noul`.
- `test_integer_with_bounds_maps_to_score`: `minimum 1, maximum 5` → criteria `["1".."5"]`, `minimum == 1`.
- `test_integer_float_bounds_that_are_integral_accepted` (`1.0`, `5.0`).
- `test_integer_missing_bound_rejected` (each side), `test_integer_exclusive_bounds_rejected`, `test_integer_single_value_rejected`, `test_integer_eleven_levels_rejected`, `test_integer_ten_levels_accepted`.
- `test_unsupported_types_rejected`: parametrized over `string` (no enum), `number`, `array`, `object`, `null`, `["string","null"]`, missing type.
- `test_combinator_keywords_rejected`: parametrized over `anyOf`, `oneOf`, `allOf`, `$ref`, `const`.
- `test_all_failures_reported_together`: three bad properties → message contains all three keys and the prefix, and the message lists supported shapes.
- `test_empty_properties_rejected`.
- `test_instructions_fallback`: description → title → None.
- `test_kiln_eval_schemas_map`: run `BaseEval.build_score_schema(eval, allow_float_scores=False)` for an `Eval` with five_star, pass_fail, pass_fail_critical and a custom score; assert the three map (score, choice, choice) and custom is absent from the schema. This pins the eval contract.

Decoding:

- `test_decode_choice`, `test_decode_integer_choice_casts_int`, `test_decode_noul_threshold` (0.5 → True, 0.4999 → False), `test_decode_score_argmax_with_offset` (levels `{"0":0.1,"1":0.6,"2":0.3}`, minimum 1 → 2), `test_decode_score_tie_picks_lowest`, `test_decode_score_empty_probabilities_falls_back_to_rounded_score`.
- `test_decode_probability_keys_use_output_values` for all four kinds.
- `test_decode_missing_answer_raises`, `test_decode_wrong_answer_type_raises`, `test_decode_choice_outside_enum_raises`.
- `test_decode_extra_answers_ignored`: answers for unknown keys do not appear in output.
- `test_roundtrip_validates_against_schema`: map → decode from synthetic answers → `validate_schema` passes, for a schema with all four kinds.
