---
status: complete
---

# Component: Jev Client (`adapters/jev/jev_client.py`)

## Purpose and Scope

A minimal async HTTP client for `POST /v1/systemone` and a single exception type that carries HTTP status and retryability. It knows nothing about Kiln tasks or JSON schemas, and it defines no wire models: those live in the reusable `jev_jsonschema` module (`SystemOneRequest`, `SystemOneResponse`, question and answer models), which this client imports.

Not in scope: retries (callers decide), the connect-flow key check (lives in `provider_api.py` using `requests`, like sibling providers; see architecture for the `/v1/models` versus minimal-POST choice), caching, streaming.

## Exception

```python
class JevApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None, retryable: bool, request_id: str | None = None): ...
```

Message text is user-facing (see the table below). `status_code` is `None` for transport errors.

## Client

```python
from kiln_ai.adapters.jev.jev_jsonschema import SystemOneRequest, SystemOneResponse

JEV_BASE_URL = "https://api.typesafe.ai"
JEV_TIMEOUT_SECONDS = 60.0

class JevClient:
    def __init__(self, api_key: str, base_url: str = JEV_BASE_URL, timeout: float = JEV_TIMEOUT_SECONDS) -> None:
        # api_key is required; Kiln's provider check has already rejected a missing key upstream.
        ...

    async def system_one(self, request: SystemOneRequest) -> SystemOneResponse: ...
```

`system_one`:

1. `body = request.to_body()` (pydantic `exclude_none`, so unset `instructions`/`criteria` are omitted, matching the SDK).
2. Headers: `Authorization: Bearer <key>`, `Content-Type: application/json`, `Accept: application/json`, `User-Agent: KilnAI`.
3. `async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client: response = await client.post("/v1/systemone", json=body, headers=headers)`. A client per call keeps the code trivially safe under the eval runner's concurrency; connection reuse is not worth the lifecycle management for one request per run.
4. Map errors per the table. Extract `request_id = response.headers.get("x-typesafe-request-id")`.
5. On 2xx: `SystemOneResponse.model_validate(response.json())`. A `ValidationError` or non-JSON body → `RuntimeError("TypeSafe AI returned an unexpected response: <first validation error or 'invalid JSON'>")`.

### Error mapping

| Condition | `JevApiError` message | `retryable` |
|---|---|---|
| `httpx.TimeoutException` | `Could not connect to TypeSafe AI. Check your network connection. (timed out)` | True |
| other `httpx.TransportError` | `Could not connect to TypeSafe AI. Check your network connection.` | True |
| 401, 403 | `Authentication with TypeSafe AI failed. Check your API key.` | False |
| 429 | `TypeSafe AI rate limit exceeded. Wait a moment and try again.` | True |
| 422 | `TypeSafe AI rejected the request: ` + `; `.join(d["msg"] for d in body["detail"]) when parseable, else the truncated body | False |
| other 4xx | `TypeSafe AI rejected the request (HTTP <code>): <body[:500]>` | False |
| 5xx | `TypeSafe AI is currently unavailable. Try again in a moment.` | True |

Bodies included in messages are truncated to 500 characters and never include headers. The key is never logged. On failure the client logs status code and request id at debug level, never the body.

## Dependencies

- `httpx` (already a `libs/core` dependency), `jev_jsonschema` models.
- Used by `JevAdapter`.

## Test Plan (`test_jev_client.py`, using `respx`)

- `test_request_shape`: captures the POSTed JSON: `state` passed through for str and dict, `model`, questions serialized with `exclude_none`, `Authorization` header, path `/v1/systemone`.
- `test_success_parses_response`: one noul, one choice, one score in the mocked response; assert a `SystemOneResponse` with typed answers, `usage`, `model`.
- `test_error_mapping` parametrized over 401, 403, 429, 422 (with and without a parseable `detail`), 400, 404, 500, 503 → message text and `retryable` flag, `status_code` set.
- `test_timeout_and_connect_errors_retryable`.
- `test_request_id_captured_on_error`.
- `test_malformed_success_body_raises_runtime_error` (non-JSON, and JSON with an answer of unknown `type`).
- `test_body_truncated_in_message`: a 4xx with a 5,000-char body yields a message under ~600 chars.
