import json
import logging
from typing import Any

import httpx
import pytest
import respx

from kiln_ai.adapters.jev.jev_client import (
    JEV_BASE_URL,
    JevApiError,
    JevClient,
)
from kiln_ai.adapters.jev.jev_jsonschema import (
    ChoiceQuestion,
    NoulQuestion,
    SystemOneRequest,
)

SYSTEM_ONE_URL = f"{JEV_BASE_URL}/v1/systemone"


@pytest.fixture
def client():
    return JevClient(api_key="sk-test-key")


def request_for(state: Any = "some content") -> SystemOneRequest:
    return SystemOneRequest(
        state=state,
        model="jev-latest",
        questions={
            "is_spam": NoulQuestion(instructions="Is this spam?"),
            "verdict": ChoiceQuestion(criteria={"pass": None, "fail": None}),
        },
    )


def success_payload() -> dict[str, Any]:
    return {
        "model": "jev-1.13.0",
        "answers": {
            "is_spam": {"type": "noul", "noul": 0.05},
            "verdict": {
                "type": "choice",
                "choice": "pass",
                "confidence": 0.9,
                "probabilities": {"pass": 0.9, "fail": 0.1},
            },
            "stars": {
                "type": "score",
                "score": 4.1,
                "confidence": 0.6,
                "legend": {"0": "1", "1": "2"},
                "probabilities": {"0": 0.1, "1": 0.9},
            },
        },
        "usage": {"input_tokens": 120, "output_tokens": 12},
    }


@pytest.mark.parametrize(
    "state", ["some content", {"task_instructions": "judge", "input": "hi"}]
)
async def test_request_shape(client: JevClient, state: Any):
    with respx.mock:
        route = respx.post(SYSTEM_ONE_URL).mock(
            return_value=httpx.Response(200, json=success_payload())
        )

        await client.system_one(request_for(state))

        sent = route.calls.last.request
        assert sent.url.path == "/v1/systemone"
        assert sent.headers["authorization"] == "Bearer sk-test-key"
        assert sent.headers["content-type"] == "application/json"
        assert sent.headers["accept"] == "application/json"
        assert sent.headers["user-agent"] == "KilnAI"
        assert json.loads(sent.content) == {
            "state": state,
            "model": "jev-latest",
            "questions": {
                # Serialized with exclude_none: no unset instructions or criteria, but
                # the choice's None option descriptions are still there.
                "is_spam": {"type": "noul", "instructions": "Is this spam?"},
                "verdict": {
                    "type": "choice",
                    "criteria": {"pass": None, "fail": None},
                },
            },
        }


async def test_success_parses_response(client: JevClient):
    with respx.mock:
        respx.post(SYSTEM_ONE_URL).mock(
            return_value=httpx.Response(200, json=success_payload())
        )

        response = await client.system_one(request_for())

    assert response.model == "jev-1.13.0"
    assert response.answers["is_spam"].noul == 0.05
    assert response.answers["verdict"].choice == "pass"
    assert response.answers["stars"].score == 4.1
    assert response.usage.input_tokens == 120
    assert response.usage.output_tokens == 12


@pytest.mark.parametrize(
    "status,body,expected_message,retryable",
    [
        (
            401,
            {"detail": "nope"},
            "Authentication with TypeSafe AI failed. Check your API key.",
            False,
        ),
        (
            403,
            {"detail": "nope"},
            "Authentication with TypeSafe AI failed. Check your API key.",
            False,
        ),
        (
            429,
            {"detail": "slow down"},
            "TypeSafe AI rate limit exceeded. Wait a moment and try again.",
            True,
        ),
        (
            422,
            {
                "detail": [
                    {"loc": ["body", "questions"], "msg": "too many questions"},
                    {"loc": ["body", "state"], "msg": "state too large"},
                ]
            },
            "TypeSafe AI rejected the request: too many questions; state too large",
            False,
        ),
        (
            422,
            {"detail": []},
            'TypeSafe AI rejected the request: {"detail":[]}',
            False,
        ),
        (
            422,
            {"message": "unprocessable"},
            'TypeSafe AI rejected the request: {"message":"unprocessable"}',
            False,
        ),
        (
            400,
            {"error": "bad model"},
            'TypeSafe AI rejected the request (HTTP 400): {"error":"bad model"}',
            False,
        ),
        (
            404,
            {"error": "no such route"},
            'TypeSafe AI rejected the request (HTTP 404): {"error":"no such route"}',
            False,
        ),
        (
            500,
            {"error": "boom"},
            "TypeSafe AI is currently unavailable. Try again in a moment.",
            True,
        ),
        (
            503,
            {"error": "maintenance"},
            "TypeSafe AI is currently unavailable. Try again in a moment.",
            True,
        ),
        (
            302,
            {"error": "moved"},
            'TypeSafe AI rejected the request (HTTP 302): {"error":"moved"}',
            False,
        ),
    ],
)
async def test_error_mapping(
    client: JevClient,
    status: int,
    body: dict[str, Any],
    expected_message: str,
    retryable: bool,
):
    with respx.mock:
        respx.post(SYSTEM_ONE_URL).mock(return_value=httpx.Response(status, json=body))

        with pytest.raises(JevApiError) as exc_info:
            await client.system_one(request_for())

    assert str(exc_info.value) == expected_message
    assert exc_info.value.status_code == status
    assert exc_info.value.retryable is retryable


@pytest.mark.parametrize(
    "error,expected_message",
    [
        (
            httpx.ConnectTimeout("too slow"),
            "Could not connect to TypeSafe AI. Check your network connection. (timed out)",
        ),
        (
            httpx.ReadTimeout("too slow"),
            "Could not connect to TypeSafe AI. Check your network connection. (timed out)",
        ),
        (
            httpx.ConnectError("no route"),
            "Could not connect to TypeSafe AI. Check your network connection.",
        ),
    ],
)
async def test_transport_errors_are_retryable(
    client: JevClient, error: Exception, expected_message: str
):
    with respx.mock:
        respx.post(SYSTEM_ONE_URL).mock(side_effect=error)

        with pytest.raises(JevApiError) as exc_info:
            await client.system_one(request_for())

    assert str(exc_info.value) == expected_message
    assert exc_info.value.retryable is True
    assert exc_info.value.status_code is None


async def test_request_id_captured_on_error(client: JevClient):
    with respx.mock:
        respx.post(SYSTEM_ONE_URL).mock(
            return_value=httpx.Response(
                500, json={}, headers={"x-typesafe-request-id": "req_abc123"}
            )
        )

        with pytest.raises(JevApiError) as exc_info:
            await client.system_one(request_for())

    assert exc_info.value.request_id == "req_abc123"
    # The request id is for logs, not for the user-facing message.
    assert "req_abc123" not in str(exc_info.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json at all"),
        httpx.Response(
            200,
            json={
                "model": "jev-latest",
                "answers": {"a": {"type": "vibes", "vibes": 1}},
            },
        ),
        httpx.Response(200, json={"answers": {}}),
    ],
)
async def test_malformed_success_body_raises_runtime_error(
    client: JevClient, response: httpx.Response
):
    with respx.mock:
        respx.post(SYSTEM_ONE_URL).mock(return_value=response)

        with pytest.raises(RuntimeError, match="unexpected response") as exc_info:
            await client.system_one(request_for())

    # Not a JevApiError: a malformed body is never retried.
    assert not isinstance(exc_info.value, JevApiError)


async def test_body_truncated_in_message(client: JevClient):
    with respx.mock:
        respx.post(SYSTEM_ONE_URL).mock(
            return_value=httpx.Response(400, text="x" * 5000)
        )

        with pytest.raises(JevApiError) as exc_info:
            await client.system_one(request_for())

    assert len(str(exc_info.value)) < 600
    assert str(exc_info.value).endswith("x" * 500)


async def test_custom_base_url_and_timeout():
    client = JevClient(api_key="k", base_url="https://example.test", timeout=1.5)

    with respx.mock:
        route = respx.post("https://example.test/v1/systemone").mock(
            return_value=httpx.Response(200, json=success_payload())
        )

        await client.system_one(request_for())

    assert route.called


async def test_failure_logging_omits_key_and_body(client: JevClient, caplog):
    with respx.mock:
        respx.post(SYSTEM_ONE_URL).mock(
            return_value=httpx.Response(
                500,
                text="echoed state and questions",
                headers={"x-typesafe-request-id": "req_1"},
            )
        )

        with caplog.at_level(logging.DEBUG, logger="kiln_ai.adapters.jev.jev_client"):
            with pytest.raises(JevApiError):
                await client.system_one(request_for())

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "req_1" in logged
    assert "500" in logged
    assert "sk-test-key" not in logged
    assert "echoed state and questions" not in logged
