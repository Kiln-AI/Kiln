---
status: complete
---

# Phase 2: `jev_jsonschema` module and `JevClient`

## Overview

Build the two pieces that carry the project's logic, both standalone and testable without
Kiln: the reusable `jev_jsonschema` module (System One wire models, JSON Schema → Jev
questions, Jev answers → JSON output plus probabilities and confidence) and the thin async
HTTP client on top of it. Nothing imports these yet; Phase 3's `JevAdapter` is the first
consumer.

`jev_jsonschema` is written for lifting into its own OSS repo: no `kiln_ai` imports, pydantic
as its only runtime dependency, relative imports internally, neutral error messages, decoding
knobs as options. Packaging and isolation tests are deferred to that repo.

Per `components/jev_client.md`, the client defines no wire models and does no retrying; the
eval runner decides retries from `JevApiError.retryable` (Phase 4).

## Steps

1. Create `libs/core/kiln_ai/adapters/jev/__init__.py` re-exporting `JevApiError`,
   `JevClient`, `JEV_BASE_URL`, `JEV_TIMEOUT_SECONDS`.

2. `libs/core/kiln_ai/adapters/jev/jev_jsonschema/models.py` — pydantic v2 mirrors of the
   System One wire models, per the component doc. Questions `extra="forbid"`; answers,
   request and response `extra="ignore"`.

   ```python
   JsonContent = str | dict[str, Any] | list[Any]

   class NoulCriteria(BaseModel):   # true / false, both optional
   class NoulQuestion(BaseModel):   # type, instructions (required), criteria
   class ChoiceQuestion(BaseModel): # criteria: dict[str, JsonContent | None], 1..255 entries
   class ScoreQuestion(BaseModel):  # criteria: list[JsonContent], 2..10 levels
   JevQuestion = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]

   class NoulAnswer(BaseModel):   # type, noul: float
   class ChoiceAnswer(BaseModel): # type, choice, confidence, probabilities
   class ScoreAnswer(BaseModel):  # type, score, confidence, legend, probabilities
   JevAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]

   class SystemOneRequest(BaseModel):
       state: JsonContent
       model: str
       questions: dict[str, JevQuestion]   # min 1
       def to_body(self) -> dict[str, Any]: return self.model_dump(exclude_none=True)

   class SystemOneUsage(BaseModel):    # input_tokens, output_tokens, both optional
   class SystemOneResponse(BaseModel): # model, answers, usage (defaults to empty)
   ```

   `exclude_none=True` drops unset `instructions`/`criteria` but keeps `None` choice-criteria
   descriptions (they are dict values, not model fields) — matching the SDK's wire shape.

3. `libs/core/kiln_ai/adapters/jev/jev_jsonschema/to_jev.py` — `PropertyFailure`,
   `IncompatibleSchemaError`, `UnexpectedAnswerError`, `ScoreDecode`, `MappingOptions`,
   `MappedKind`, `MappedQuestion`, `QuestionSet`, `JSONSchema2Jev`, with the signatures in the
   component doc. `IncompatibleSchemaError.failures` is a tuple and
   `str(err) == "Schema has properties that cannot be mapped to Jev questions:\n- key: reason..."`.

   `convert` rejects a non-object root or absent/empty `properties` with a single `<root>`
   failure, then maps each property in schema order, collecting every failure before raising.
   `_map_property` follows the component doc's decision order: combinator keywords, `enum`
   (string choice / integer choice, then duplicate and 255-option checks), `boolean` → noul,
   `number` with bounds exactly 0 and 1 → noul with `criteria.true = X` /
   `criteria.false = "inverse of X"`, `integer` with integral `minimum` and `maximum` spanning
   2..`max_score_levels` → score with `criteria = [str(minimum) … str(maximum)]`, a list `type`
   → "multiple types", else unsupported type / "no type or enum".

   `_instructions` is `description`, else `title` (each a non-blank string), else the property
   key when `instructions_fallback_to_key`, else `None`. Numeric bound helpers reject `bool`
   (`True == 1` in Python) and accept integral floats such as `5.0`.

4. `libs/core/kiln_ai/adapters/jev/jev_jsonschema/from_jev.py` — `DecodedResult` and
   `JevResult2JsonSchema`, per the component doc's decoding table. Answers arrive as typed
   models or raw dicts (validated through the `JevAnswer` union). Missing answer, wrong answer
   type for the question, a choice label outside the enum, or an out-of-range score level raise
   `UnexpectedAnswerError`; extra answers are ignored; probabilities are unrounded and keyed by
   output value (`"true"`/`"false"` for nouls, `str(minimum + level)` for scores).

5. `libs/core/kiln_ai/adapters/jev/jev_jsonschema/__init__.py` — re-export exactly the public
   names listed in the component doc.

6. `libs/core/kiln_ai/adapters/jev/jev_client.py` — `JEV_BASE_URL`, `JEV_TIMEOUT_SECONDS`,
   `JevApiError(RuntimeError)` carrying `status_code`/`retryable`/`request_id`, and
   `JevClient.system_one` posting `request.to_body()` to `/v1/systemone` with the Bearer,
   content-type, accept and `KilnAI` user-agent headers, one `httpx.AsyncClient` per call.
   Errors map per the component doc's table (timeout before other transport errors, since
   `TimeoutException` subclasses `TransportError`); non-2xx statuses outside the table's rows
   fall through to the "rejected the request (HTTP n)" form. Bodies in messages truncate to 500
   characters; a non-JSON or unparseable 2xx body raises
   `RuntimeError("TypeSafe AI returned an unexpected response: …")`. Failures log status code
   and `x-typesafe-request-id` at debug level only — never the body or the key.

## Tests

`jev_jsonschema/test_models.py`
- `test_question_serialization_omits_unset_and_keeps_none_criteria` — unset `instructions`/`criteria` dropped by `to_body`, `None` choice descriptions kept.
- `test_score_question_level_limits` / `test_choice_question_option_limits` / `test_noul_question_requires_instructions` — 1 and 11 score levels rejected, 2 and 10 accepted; 0 and 256 choice options rejected; noul without instructions rejected.
- `test_answers_ignore_unknown_fields`, `test_response_parses_all_answer_types`, `test_response_usage_defaults`.
- `test_request_to_body_matches_documented_example` — the research doc's example request.

`jev_jsonschema/test_to_jev.py`
- `test_string_enum` (with and without `type`), `test_integer_enum` (labels are `str(value)`), parametrized `test_enum_rejected` (bool, mixed, empty, duplicate, type mismatch, 256 values).
- `test_boolean_instructions_fallback` — description, then title, then key; `instructions_fallback_to_key=False` with no description rejected.
- `test_number_probability_criteria` — `criteria.true == X`, `criteria.false == f"inverse of {X}"`; `0.0`/`1.0` bounds accepted; parametrized `test_number_rejected` (other bounds, missing bounds).
- `test_integer_score_levels` — criteria and stored `minimum`; integral floats accepted; parametrized `test_integer_rejected` (missing bound, exclusive bounds, single value, 11 levels); 10 accepted; `max_score_levels=5` honoured.
- `test_unsupported_types_and_combinators` — string without enum, array, object, null, list of types, no type, and each of `anyOf`/`oneOf`/`allOf`/`$ref`/`const`/`not`.
- `test_root_rejected` — non-object type, missing properties, empty properties, all keyed `<root>`.
- `test_all_failures_reported_in_schema_order` — `err.failures` and `str(err)` list every bad property in order.
- `test_question_set_questions_and_request` — `.questions` mirrors mappings; `.request(state, model)` round-trips through `to_body`.

`jev_jsonschema/test_from_jev.py`
- `test_string_choice`, `test_integer_choice_casts`, `test_boolean_noul_threshold` (0.5 boundary and a custom threshold), `test_number_noul_returns_float`.
- `test_score_argmax_with_offset`, `test_score_argmax_tie_picks_lowest`, `test_score_decode_expected_rounds_and_clamps`, `test_score_empty_probabilities_falls_back_to_expected`.
- `test_probabilities_keyed_by_output_values`, `test_confidence_none_for_noul_kinds`.
- `test_raw_dict_answers_accepted`, `test_invalid_raw_dict_answer_raises`.
- parametrized `test_unexpected_answer_errors` — missing answer, wrong answer type per kind, choice outside the enum, out-of-range score level.
- `test_extra_answers_ignored`.
- `test_round_trip_validates_against_schema` — a schema with all five kinds decoded and validated with `jsonschema`.

`test_jev_client.py` (respx)
- `test_request_shape` — path, Bearer and user-agent headers, `state` for str and dict, `model`, questions serialized with `exclude_none`.
- `test_success_parses_response` — one noul, one choice, one score, plus `usage` and `model`.
- parametrized `test_error_mapping` — 401, 403, 429, 422 (with and without parseable `detail`), 400, 404, 500, 503 → message, `retryable`, `status_code`.
- `test_timeout_and_connect_errors_retryable`.
- `test_request_id_captured_on_error`.
- `test_malformed_success_body_raises_runtime_error` — non-JSON body, and JSON with an unknown answer `type`.
- `test_body_truncated_in_message` — a 5,000-character 4xx body yields a message under 600 characters.
