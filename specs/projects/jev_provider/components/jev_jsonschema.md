---
status: draft
---

# Component: `jev_jsonschema` (reusable module)

## Purpose and Scope

A small module that converts between JSON Schema and TypeSafe Jev's question/answer format, in both directions:

- `JSONSchema2Jev`: JSON Schema object → a set of Jev questions.
- `JevResult2JsonSchema`: Jev answers → a JSON object matching that schema, plus per-property probabilities and confidence.

It is written for reuse outside Kiln: no `kiln_ai` imports (by convention, not enforced), `pydantic>=2` as its only dependency, relative imports internally, neutral error messages, and the decoding knobs exposed as options. It also owns the System One wire models so a consumer needs nothing else to build a request and parse a response. Packaging, README, and isolation tests are deferred to the future standalone repo.

Not in scope: HTTP, building the `state`, validating the decoded output against the schema (callers do that; Kiln's base adapter already does).

## Layout

```
libs/core/kiln_ai/adapters/jev/jev_jsonschema/
  __init__.py      # re-exports below
  models.py        # wire models
  to_jev.py        # JSONSchema2Jev, QuestionSet, MappedQuestion, MappedKind, MappingOptions, ScoreDecode, errors
  from_jev.py      # JevResult2JsonSchema, DecodedResult
  test_models.py  test_to_jev.py  test_from_jev.py
```

## Public interface (`__init__.py` exports)

```python
from .from_jev import DecodedResult, JevResult2JsonSchema
from .models import (
    ChoiceAnswer, ChoiceQuestion, JevAnswer, JevQuestion, JsonContent,
    NoulAnswer, NoulCriteria, NoulQuestion, ScoreAnswer, ScoreQuestion,
    SystemOneRequest, SystemOneResponse, SystemOneUsage,
)
from .to_jev import (
    IncompatibleSchemaError, JSONSchema2Jev, MappedKind, MappedQuestion,
    MappingOptions, PropertyFailure, QuestionSet, ScoreDecode, UnexpectedAnswerError,
)
```

### `models.py`

Pydantic v2 mirrors of the API's OpenAPI models (see `research/jev_api/summary.md`). Questions use `extra="forbid"`; answers, request and response use `extra="ignore"` for forward compatibility.

```python
JsonContent = str | dict[str, Any] | list[Any]

class NoulCriteria(BaseModel):
    true: JsonContent | None = None
    false: JsonContent | None = None

class NoulQuestion(BaseModel):
    type: Literal["noul"] = "noul"
    instructions: JsonContent                 # required by the API docs
    criteria: NoulCriteria | None = None

class ChoiceQuestion(BaseModel):
    type: Literal["choice"] = "choice"
    instructions: JsonContent | None = None
    criteria: dict[str, JsonContent | None]   # validator: 1..255 entries

class ScoreQuestion(BaseModel):
    type: Literal["score"] = "score"
    instructions: JsonContent | None = None
    criteria: list[JsonContent]               # validator: 2..10 levels

JevQuestion = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]

class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float

class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    confidence: float
    probabilities: dict[str, float]

class ScoreAnswer(BaseModel):
    type: Literal["score"]
    score: float
    confidence: float
    legend: dict[str, JsonContent]
    probabilities: dict[str, float]           # keys are 0-based level indices as strings

JevAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]

class SystemOneRequest(BaseModel):
    state: JsonContent
    model: str
    questions: dict[str, JevQuestion]         # min 1
    def to_body(self) -> dict[str, Any]: return self.model_dump(exclude_none=True)

class SystemOneUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None

class SystemOneResponse(BaseModel):
    model: str
    answers: dict[str, JevAnswer]
    usage: SystemOneUsage = SystemOneUsage()
```

### `to_jev.py`

```python
@dataclass(frozen=True)
class PropertyFailure:
    key: str
    reason: str

class IncompatibleSchemaError(ValueError):
    failures: tuple[PropertyFailure, ...]
    # str(err) == "Schema has properties that cannot be mapped to Jev questions:\n- key: reason\n..."

class UnexpectedAnswerError(RuntimeError):
    """An answer is missing, has the wrong type for its question, or an out-of-range value."""

class ScoreDecode(str, Enum):
    argmax = "argmax"        # level with the highest probability, lowest on tie
    expected = "expected"    # round(answer.score), clamped

@dataclass(frozen=True)
class MappingOptions:
    noul_threshold: float = 0.5
    max_score_levels: int = 10
    score_decode: ScoreDecode = ScoreDecode.argmax
    instructions_fallback_to_key: bool = True   # description → title → property key

class MappedKind(str, Enum):
    string_choice = "string_choice"
    integer_choice = "integer_choice"
    boolean_noul = "boolean_noul"
    number_noul = "number_noul"
    score = "score"

@dataclass(frozen=True)
class MappedQuestion:
    key: str
    kind: MappedKind
    question: NoulQuestion | ChoiceQuestion | ScoreQuestion
    enum_values: tuple[str | int, ...] | None = None   # choice kinds, schema order
    minimum: int | None = None                          # score kind: value of level 0

@dataclass(frozen=True)
class QuestionSet:
    mappings: dict[str, MappedQuestion]                 # schema property order
    @property
    def questions(self) -> dict[str, JevQuestion]: ...
    def request(self, state: JsonContent, model: str) -> SystemOneRequest: ...

class JSONSchema2Jev:
    def __init__(self, options: MappingOptions = MappingOptions()) -> None: ...
    def convert(self, schema: Mapping[str, Any]) -> QuestionSet:
        """Raises IncompatibleSchemaError listing every unmappable property."""
```

### `from_jev.py`

```python
@dataclass(frozen=True)
class DecodedResult:
    output: dict[str, Any]                       # validates against the source schema
    probabilities: dict[str, dict[str, float]]   # property → {output value as str: p}
    confidence: dict[str, float | None]          # property → confidence, None for noul kinds

class JevResult2JsonSchema:
    def __init__(self, options: MappingOptions = MappingOptions()) -> None: ...
    def convert(
        self,
        question_set: QuestionSet,
        answers: Mapping[str, JevAnswer | Mapping[str, Any]],   # typed models or raw JSON dicts
    ) -> DecodedResult:
        """Raises UnexpectedAnswerError on a missing/mismatched/out-of-range answer."""
```

Accepting raw dicts means a consumer can pass `response.json()["answers"]` straight in.

## Mapping algorithm (`JSONSchema2Jev.convert`)

```
if schema.get("type") not in (None, "object") or not isinstance(schema.get("properties"), dict):
    raise IncompatibleSchemaError([PropertyFailure("<root>", "schema must be an object with properties")])
properties = schema["properties"]
if not properties: raise IncompatibleSchemaError([PropertyFailure("<root>", "schema has no properties")])
mappings, failures = {}, []
for key, prop in properties.items():                 # dict order == schema order
    try: mappings[key] = self._map_property(key, prop)
    except _Unsupported as e: failures.append(PropertyFailure(key, str(e)))
if failures: raise IncompatibleSchemaError(failures)
return QuestionSet(mappings)
```

`_instructions(key, prop) -> str | None`: `description` if a non-empty string, else `title` if non-empty, else `key` when `instructions_fallback_to_key`, else `None`. Call it X below.

`_map_property(key, prop)` decision order; first match wins:

1. Any of `anyOf`, `oneOf`, `allOf`, `$ref`, `const`, `not` present → "uses '<keyword>', which is not supported".
2. `enum` present:
   - empty → "enum has no values".
   - all `str` and `type` in (absent, `"string"`) → `string_choice`, criteria `{value: None}` in order.
   - all `int` (excluding `bool`) and `type` in (absent, `"integer"`) → `integer_choice`, criteria `{str(value): None}`.
   - duplicates after `str()` → "enum has duplicate values".
   - more than 255 values → "enum has N values; Jev choice supports at most 255".
   - otherwise → "enum values must be all strings or all integers and match the declared type".
   - `instructions = X` (omitted when None).
3. `type == "boolean"` → `boolean_noul`, `NoulQuestion(instructions=X)`. X None → "boolean needs a description".
4. `type == "number"`:
   - `minimum == 0` and `maximum == 1` (accept `0.0`/`1.0`) → `number_noul`, `NoulQuestion(instructions=X, criteria=NoulCriteria(true=X, false=f"inverse of {X}"))`. X None → "number needs a description".
   - otherwise → "number is only supported with minimum 0 and maximum 1 (mapped to a probability)".
5. `type == "integer"`:
   - `minimum` and `maximum` both present and integral (accept `5.0`) → `levels = maximum - minimum + 1`.
   - a bound missing or non-integral → "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)".
   - `levels < 2` → "integer range must span at least 2 values"; `levels > options.max_score_levels` → "integer range spans N values; Jev score supports at most M".
   - else `score`, `ScoreQuestion(instructions=X, criteria=[str(v) for v in range(minimum, maximum + 1)])`, `minimum` stored.
6. `type` is a list → "multiple types are not supported".
7. Anything else → "type '<t>' is not supported" or "no type or enum".

## Decoding algorithm (`JevResult2JsonSchema.convert`)

For each `key, mapping` in `question_set.mappings` (schema order):

- Fetch `answers[key]`; missing → `UnexpectedAnswerError(f"no answer for '{key}'")`. A raw dict is validated through the `JevAnswer` union first; failure → `UnexpectedAnswerError` with the pydantic message.
- Type check: noul kinds ↔ `NoulAnswer`, choice kinds ↔ `ChoiceAnswer`, `score` ↔ `ScoreAnswer`; mismatch → `UnexpectedAnswerError(f"answer for '{key}' has type '{t}', expected '{e}'")`.

| kind | `output[key]` | `probabilities[key]` | `confidence[key]` |
|---|---|---|---|
| `string_choice` | `answer.choice` (must be in `enum_values`, else error) | `dict(answer.probabilities)` | `answer.confidence` |
| `integer_choice` | `int(answer.choice)` | same | `answer.confidence` |
| `boolean_noul` | `answer.noul >= options.noul_threshold` | `{"true": p, "false": 1 - p}` | `None` |
| `number_noul` | `answer.noul` (float) | `{"true": p, "false": 1 - p}` | `None` |
| `score` | argmax: `minimum + min(level with max p)`; expected: `clamp(round(answer.score)) + minimum`; empty `probabilities` always falls back to expected | `{str(minimum + level): p}` | `answer.confidence` |

Extra answers not in the question set are ignored. Probabilities are returned unrounded.

## Dependencies

- `pydantic>=2`. Nothing else.
- Used by: Kiln's `JevClient` (wire models) and `JevAdapter` (both converters).

## Test Plan

`test_models.py`
- Question serialization drops unset optional fields, keeps user-supplied `None` criteria descriptions.
- `ScoreQuestion` rejects 1 and 11 levels, accepts 2 and 10. `ChoiceQuestion` rejects 0 and 256 options. `NoulQuestion` requires `instructions`.
- Answers and response ignore unknown fields; `SystemOneResponse` parses all three answer types; `usage` defaults.
- `SystemOneRequest.to_body()` matches the documented example request.

`test_to_jev.py` (parametrize where natural)
- string enum with and without `type`; integer enum; bool/mixed/empty/duplicate/type-mismatch enums rejected; 256-value enum rejected.
- boolean → noul with instructions from description, title, then key; no fallback and no description → rejected.
- number 0..1 → noul with `criteria.true == X` and `criteria.false == f"inverse of {X}"`; number with other bounds or no bounds rejected; `0.0`/`1.0` accepted.
- integer bounds → score with correct criteria and `minimum`; float-integral bounds accepted; missing bound, exclusive bounds, single value, 11 levels rejected; 10 accepted; `max_score_levels=5` honoured.
- unsupported types and combinators rejected; root not an object / no properties rejected with key `<root>`.
- all failures reported together, in schema order, in `err.failures` and `str(err)`.
- `QuestionSet.questions` and `.request(state, model)` produce a serializable request.
- Kiln contract (this test lives in Kiln's adapter tests, not here): `BaseEval.build_score_schema` output for five_star, pass_fail, pass_fail_critical maps to score, choice, choice.

`test_from_jev.py`
- choice; integer choice casts; boolean noul threshold at 0.5 and custom; number noul returns the float; score argmax with offset; tie picks lowest; `ScoreDecode.expected` rounds and clamps; empty probabilities falls back.
- probabilities keyed by output values for all kinds; confidence populated, `None` for noul kinds.
- raw dict answers accepted; invalid raw dict → `UnexpectedAnswerError`.
- missing answer, wrong type, choice outside enum → `UnexpectedAnswerError`.
- extra answers ignored.
- round trip: schema with all five kinds → synthetic answers → `jsonschema` validation passes.
