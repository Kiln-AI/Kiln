---
status: draft
---

# Component: `jev_jsonschema` (standalone, extractable package)

## Purpose and Scope

A small, self-contained Python package that converts between JSON Schema and TypeSafe Jev's question/answer format, in both directions:

- `JSONSchema2Jev`: JSON Schema object → a set of Jev questions.
- `JevResult2JsonSchema`: Jev answers → a JSON object matching that schema, plus per-property probability distributions.

It is designed to be lifted out of Kiln into its own open-source project unchanged. Hard rules:

- **No imports from `kiln_ai`** (enforced by a test that scans the package source).
- **Only dependency: `pydantic>=2`.** Everything else is stdlib.
- **Relative imports only** inside the package.
- **Neutral wording.** Errors describe the schema problem; they never mention Kiln, tasks, or settings. Kiln's adapter adds its own prefix.
- Ships its own `README.md`, `py.typed`, and tests, all inside the package directory.
- Also owns the wire models for the System One request and response, so an OSS user has everything needed to build a request and parse a response without another dependency. Kiln's HTTP client imports these models rather than defining its own.

Not in scope: HTTP, building the `state`, validating the decoded output against the schema (callers do that with their own validator; Kiln's base adapter already does).

## Location and layout

```
libs/core/kiln_ai/adapters/jev/jev_jsonschema/
  __init__.py          # public re-exports
  README.md
  py.typed
  models.py            # System One wire models (questions, answers, request, response)
  errors.py            # IncompatibleSchemaError, UnexpectedAnswerError, PropertyFailure
  options.py           # MappingOptions
  to_jev.py            # JSONSchema2Jev, QuestionSet, MappedQuestion, MappedKind
  from_jev.py          # JevResult2JsonSchema, DecodedResult
  test_models.py
  test_to_jev.py
  test_from_jev.py
  test_package_isolation.py
```

Kiln imports it as `kiln_ai.adapters.jev.jev_jsonschema`. Extraction is `cp -r` plus a `pyproject.toml`.

## Public interface (`__init__.py` exports)

```python
from .errors import IncompatibleSchemaError, PropertyFailure, UnexpectedAnswerError
from .from_jev import DecodedResult, JevResult2JsonSchema
from .models import (
    ChoiceAnswer, ChoiceQuestion, JevAnswer, JevQuestion, JsonContent,
    NoulAnswer, NoulCriteria, NoulQuestion, ScoreAnswer, ScoreQuestion,
    SystemOneRequest, SystemOneResponse, SystemOneUsage,
)
from .options import MappingOptions, ScoreDecode
from .to_jev import JSONSchema2Jev, MappedKind, MappedQuestion, QuestionSet
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
    instructions: JsonContent            # required by the docs for noul
    criteria: NoulCriteria | None = None

class ChoiceQuestion(BaseModel):
    type: Literal["choice"] = "choice"
    instructions: JsonContent | None = None
    criteria: dict[str, JsonContent | None]     # min 1 entry; validator enforces <= 255

class ScoreQuestion(BaseModel):
    type: Literal["score"] = "score"
    instructions: JsonContent | None = None
    criteria: list[JsonContent]                 # validator enforces 2..10 levels

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
    probabilities: dict[str, float]             # keys are 0-based level indices as strings

JevAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]

class SystemOneRequest(BaseModel):
    state: JsonContent
    model: str
    questions: dict[str, JevQuestion]           # min 1
    def to_body(self) -> dict[str, Any]: return self.model_dump(exclude_none=True)

class SystemOneUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None

class SystemOneResponse(BaseModel):
    model: str
    answers: dict[str, JevAnswer]
    usage: SystemOneUsage = SystemOneUsage()
```

Limits verified against the primitives docs: Score 2 to 10 levels, Choice up to 255 options. The model validators enforce them so a bad question never leaves the process.

### `errors.py`

```python
@dataclass(frozen=True)
class PropertyFailure:
    key: str
    reason: str          # e.g. "type 'string' without enum is not supported"

class IncompatibleSchemaError(ValueError):
    failures: tuple[PropertyFailure, ...]
    def __init__(self, failures: Sequence[PropertyFailure]): ...
    # str(err) == "Schema has properties that cannot be mapped to Jev questions:\n- key: reason\n- ..."

class UnexpectedAnswerError(RuntimeError):
    """An answer is missing, has the wrong type for its question, or an out-of-range value."""
```

Kiln catches `IncompatibleSchemaError` and rewrites it into its own `ValueError` using `.failures`, so Kiln's wording never leaks into the package.

### `options.py`

```python
class ScoreDecode(str, Enum):
    argmax = "argmax"        # level with the highest probability, lowest on tie
    expected = "expected"    # round(answer.score), clamped

@dataclass(frozen=True)
class MappingOptions:
    noul_threshold: float = 0.5
    max_score_levels: int = 10
    score_decode: ScoreDecode = ScoreDecode.argmax
    instructions_fallback_to_key: bool = True   # description → title → property key
```

### `to_jev.py`

```python
class MappedKind(str, Enum):
    string_choice = "string_choice"
    integer_choice = "integer_choice"
    noul = "noul"
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
    def questions(self) -> dict[str, JevQuestion]: ...  # ready for SystemOneRequest.questions
    def request(self, state: JsonContent, model: str) -> SystemOneRequest: ...

class JSONSchema2Jev:
    def __init__(self, options: MappingOptions = MappingOptions()) -> None: ...
    def convert(self, schema: Mapping[str, Any]) -> QuestionSet:
        """Raises IncompatibleSchemaError listing every unmappable property."""
```

Also exported as a convenience: `json_schema_to_jev(schema, options=...)`.

### `from_jev.py`

```python
@dataclass(frozen=True)
class DecodedResult:
    output: dict[str, Any]                       # validates against the source schema
    probabilities: dict[str, dict[str, float]]   # property → {output value as str: p}
    confidence: dict[str, float | None]          # property → confidence (None for noul)

class JevResult2JsonSchema:
    def __init__(self, options: MappingOptions = MappingOptions()) -> None: ...
    def convert(
        self,
        question_set: QuestionSet,
        answers: Mapping[str, JevAnswer | Mapping[str, Any]],   # typed models or raw JSON dicts
    ) -> DecodedResult:
        """Raises UnexpectedAnswerError on a missing/mismatched/out-of-range answer."""
```

Also exported: `jev_result_to_json_schema(question_set, answers, options=...)`. Accepting raw dicts means an OSS user can pass `response.json()["answers"]` straight in.

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

`_map_property(key, prop)` decision order; first match wins:

1. Any of `anyOf`, `oneOf`, `allOf`, `$ref`, `const`, `not` present → "uses '<keyword>', which is not supported".
2. `enum` present:
   - empty → "enum has no values".
   - all `str` and `type` in (absent, `"string"`) → `string_choice`, criteria `{value: None}` in order.
   - all `int` (excluding `bool`) and `type` in (absent, `"integer"`) → `integer_choice`, criteria `{str(value): None}`.
   - duplicates after `str()` → "enum has duplicate values".
   - more than 255 values → "enum has N values; Jev choice supports at most 255".
   - otherwise → "enum values must be all strings or all integers and match the declared type".
3. `type == "boolean"` → `noul`. `instructions` is required by the API, so it is the description, else title, else the property key (when `instructions_fallback_to_key`), else "uses boolean without a description".
4. `type == "integer"`:
   - `minimum` and `maximum` both present and integral (accept `5.0`) → `levels = maximum - minimum + 1`.
   - a bound missing or non-integral → "integer needs integer 'minimum' and 'maximum' (exclusive bounds are not supported)".
   - `levels < 2` → "integer range must span at least 2 values"; `levels > options.max_score_levels` → "integer range spans N values; Jev score supports at most M".
   - else `score` with `criteria = [str(v) for v in range(minimum, maximum + 1)]`, `minimum` stored.
5. `type` is a list → "multiple types are not supported".
6. Anything else → "type '<t>' is not supported" or "no type or enum".

Instructions for choice and score: description, else title, else the key when the fallback option is on, else omitted (they are optional for those types).

## Decoding algorithm (`JevResult2JsonSchema.convert`)

For each `key, mapping` in `question_set.mappings` (schema order):

- Fetch `answers[key]`; missing → `UnexpectedAnswerError(f"no answer for '{key}'")`. A raw dict is validated through the `JevAnswer` discriminated union first; a validation failure → `UnexpectedAnswerError` with the pydantic message.
- Type check: `noul` ↔ `NoulAnswer`, choice kinds ↔ `ChoiceAnswer`, `score` ↔ `ScoreAnswer`; mismatch → `UnexpectedAnswerError(f"answer for '{key}' has type '{t}', expected '{e}'")`.

| kind | `output[key]` | `probabilities[key]` | `confidence[key]` |
|---|---|---|---|
| `string_choice` | `answer.choice` (must be in `enum_values`, else error) | `dict(answer.probabilities)` | `answer.confidence` |
| `integer_choice` | `int(answer.choice)` | same | `answer.confidence` |
| `noul` | `answer.noul >= options.noul_threshold` | `{"true": p, "false": 1 - p}` | `None` |
| `score` | argmax: `minimum + min(level for level with max p)`; expected: `clamp(round(answer.score)) + minimum`; empty `probabilities` always falls back to expected | `{str(minimum + level): p}` | `answer.confidence` |

Extra answers not in the question set are ignored. Probabilities are returned unrounded.

## Dependencies

- `pydantic>=2`. Nothing else.
- Used by: Kiln's `JevClient` (wire models) and `JevAdapter` (both converters).

## README contents

Install, a 15-line example (schema → request body → POST with `httpx` or `requests` → decode), the supported-shapes table, the options table, and a note that the output should still be validated with a JSON Schema validator of the caller's choice.

## Test Plan

`test_package_isolation.py`
- `test_no_kiln_imports`: walk every `.py` in the package and assert `kiln_ai` does not appear in any import line.
- `test_only_relative_imports_within_package`: any import of a sibling module uses a relative form.

`test_models.py`
- Question serialization drops unset optional fields (`exclude_none`), keeps user-supplied `None` criteria descriptions.
- `ScoreQuestion` rejects 1 level and 11 levels, accepts 2 and 10.
- `ChoiceQuestion` rejects 0 options and 256 options.
- `NoulQuestion` requires `instructions`.
- Answers and response ignore unknown fields; `SystemOneResponse` parses the three answer types; `usage` defaults.
- `SystemOneRequest.to_body()` round-trips to the documented example request.

`test_to_jev.py` (parametrize where natural)
- string enum with and without `type`; integer enum; bool/mixed/empty/duplicate/type-mismatch enums rejected; 256-value enum rejected.
- boolean → noul with instructions from description, title, then key; fallback disabled and no description → rejected.
- integer bounds → score with correct criteria and `minimum`; float-integral bounds accepted; missing bound, exclusive bounds, single value, 11 levels rejected; 10 accepted; `max_score_levels=5` option honoured.
- unsupported types (`string` w/o enum, `number`, `array`, `object`, `null`, type list, no type) rejected.
- combinators (`anyOf`, `oneOf`, `allOf`, `$ref`, `const`, `not`) rejected.
- root not an object / no properties rejected with key `<root>`.
- all failures reported together, in schema order, with keys and reasons in `err.failures` and in `str(err)`.
- `QuestionSet.questions` and `.request(state, model)` produce a serializable `SystemOneRequest`.

`test_from_jev.py`
- choice; integer choice casts; noul threshold at 0.5 and custom threshold; score argmax with offset; tie picks lowest; `ScoreDecode.expected` rounds and clamps; empty probabilities falls back.
- probabilities keyed by output values for all four kinds; confidence populated and `None` for noul.
- raw dict answers accepted; invalid raw dict → `UnexpectedAnswerError`.
- missing answer, wrong type, choice outside enum → `UnexpectedAnswerError`.
- extra answers ignored.
- round trip: convert a schema with all four kinds, decode synthetic answers, validate with `jsonschema` (test-only dependency; already in Kiln's env).

Kiln-side contract test (lives in Kiln, not the package): `BaseEval.build_score_schema` output for five_star, pass_fail, pass_fail_critical converts to score, choice, choice.
