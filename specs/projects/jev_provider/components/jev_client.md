---
status: draft
---

# Component: Jev Client (`adapters/jev/jev_client.py`)

## Purpose and Scope

A minimal async client for `POST /v1/systemone` plus the Pydantic wire models for questions and answers, and a single exception type that carries HTTP status and retryability. It knows nothing about Kiln tasks or JSON schemas.

Not in scope: retries (callers decide), the `GET /v1/models` connection check (lives in `provider_api.py` using `requests`, like sibling providers), caching, streaming.

## Wire models

Mirror the OpenAPI-generated models in `typesafe-sdk` (see `research/jev_api/summary.md`). Pydantic v2, `extra="ignore"` on answers and the response so new API fields never break parsing; `extra="forbid"` on questions so mapping bugs fail loudly in tests.

```python
JsonContent = str | dict[str, Any] | list[Any]

class NoulQuestion(BaseModel):
    type: Literal["noul"] = "noul"
    instructions: JsonContent | None = None
    criteria: NoulCriteria | None = None          # {"true": desc | None, "false": desc | None}

class ChoiceQuestion(BaseModel):
    type: Literal["choice"] = "choice"
    instructions: JsonContent | None = None
    criteria: dict[str, JsonContent | None]

class ScoreQuestion(BaseModel):
    type: Literal["score"] = "score"
    instructions: JsonContent | None = None
    criteria: list[JsonContent]                    # min_length=1

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
    probabilities: dict[str, float]                # keys are level indices as strings

JevAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]

class JevUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None

class JevResponse(BaseModel):
    model: str
    answers: dict[str, JevAnswer]
    usage: JevUsage = JevUsage()
```

Request serialization: `question.model_dump(exclude_none=True)` so unset `instructions`/`criteria` are omitted, matching the SDK.

## Exception

```python
class JevApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None, retryable: bool, request_id: str | None = None): ...
```

Message text is user-facing (see the table below). `status_code` is `None` for transport errors.

## Client

```python
JEV_BASE_URL = "https://api.typesafe.ai"
JEV_TIMEOUT_SECONDS = 60.0

class JevClient:
    def __init__(self, api_key: str, base_url: str = JEV_BASE_URL, timeout: float = JEV_TIMEOUT_SECONDS) -> None:
        if not api_key:
            raise ValueError("TypeSafe AI API key not set. Connect TypeSafe AI in Settings → AI Providers.")
        ...

    async def system_one(
        self,
        state: JsonContent,
        model: str,
        questions: Mapping[str, NoulQuestion | ChoiceQuestion | ScoreQuestion],
    ) -> JevResponse: ...
```

`system_one`:

1. `if not questions: raise ValueError("At least one question is required.")` (defensive; the adapter never sends zero).
2. Body: `{"state": state, "model": model, "questions": {name: q.model_dump(exclude_none=True)}}`.
3. Headers: `Authorization: Bearer <key>`, `Content-Type: application/json`, `Accept: application/json`, `User-Agent: KilnAI`.
4. `async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client: response = await client.post("/v1/systemone", json=body, headers=headers)`. A client per call keeps the code trivially safe under the eval runner's concurrency; connection reuse is not worth the lifecycle management for one request per run.
5. Map errors per the table. Extract `request_id = response.headers.get("x-typesafe-request-id")`.
6. On 2xx: `JevResponse.model_validate(response.json())`. A `ValidationError` or non-JSON body → `RuntimeError("TypeSafe AI returned an unexpected response: <first validation error or 'invalid JSON'>")`.

### Error mapping

| Condition | `JevApiError` message | `retryable` |
|---|---|---|
| `httpx.TimeoutException` | `Could not connect to TypeSafe AI. Check your network connection.` (append ` (timed out)`) | True |
| other `httpx.TransportError` | `Could not connect to TypeSafe AI. Check your network connection.` | True |
| 401, 403 | `Authentication with TypeSafe AI failed. Check your API key.` | False |
| 429 | `TypeSafe AI rate limit exceeded. Wait a moment and try again.` | True |
| 422 | `TypeSafe AI rejected the request: ` + `; `.join(d["msg"] for d in body["detail"]) when parseable, else the truncated body | False |
| other 4xx | `TypeSafe AI rejected the request (HTTP <code>): <body[:500]>` | False |
| 5xx | `TypeSafe AI is currently unavailable. Try again in a moment.` | True |

Bodies included in messages are truncated to 500 characters and never include headers. The key is never logged.

## Dependencies

- `httpx` (already a `libs/core` dependency), `pydantic`.
- Used by `JevAdapter`; wire models imported by `jev_schema_mapping.py`.

## Test Plan (`test_jev_client.py`, using `respx`)

- `test_request_shape`: captures the POSTed JSON: `state` passed through for str and dict, `model`, questions serialized with `exclude_none` (no `instructions` key when unset, `criteria` present for choice/score), `Authorization` header, path `/v1/systemone`.
- `test_success_parses_all_answer_types`: one noul, one choice, one score in the mocked response; assert typed answers, `usage`, `model`.
- `test_unknown_fields_ignored`: extra keys at response, answer and usage level parse fine.
- `test_missing_usage_defaults_to_none`.
- `test_error_mapping` parametrized over 401, 403, 429, 422 (with and without a parseable `detail`), 400, 404, 500, 503 → message text and `retryable` flag, `status_code` set.
- `test_timeout_and_connect_errors_retryable`.
- `test_request_id_captured_on_error`.
- `test_malformed_success_body_raises_runtime_error` (non-JSON, and JSON with an answer of unknown `type`).
- `test_empty_api_key_rejected_at_construction`, `test_empty_questions_rejected`.
- `test_body_truncated_in_message`: a 4xx with a 5,000-char body yields a message under ~600 chars.
