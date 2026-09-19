"""HTTP client for TypeSafe AI's System One API.

One POST, no retries, no streaming: callers decide whether to retry from
`JevApiError.retryable`. Wire models live in `jev_jsonschema` so this file holds only
transport and error mapping.
"""

import logging
from typing import Any

import httpx
from pydantic import ValidationError

from kiln_ai.adapters.jev.jev_jsonschema import SystemOneRequest, SystemOneResponse

logger = logging.getLogger(__name__)

JEV_BASE_URL = "https://api.typesafe.ai"
JEV_TIMEOUT_SECONDS = 60.0
SYSTEM_ONE_PATH = "/v1/systemone"
REQUEST_ID_HEADER = "x-typesafe-request-id"

MAX_BODY_CHARS_IN_MESSAGE = 500


class JevApiError(RuntimeError):
    """A call to TypeSafe AI failed. The message is user-facing."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None,
        retryable: bool,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.request_id = request_id


class JevClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = JEV_BASE_URL,
        timeout: float = JEV_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout

    async def system_one(self, request: SystemOneRequest) -> SystemOneResponse:
        """Ask Jev every question in the request against its state.

        Raises:
            JevApiError: transport failure or a non-2xx response.
            RuntimeError: a 2xx response that is not a System One response.
        """
        body = request.to_body()
        try:
            # A client per call keeps this trivially safe under the eval runner's
            # concurrency; there is only one request per run to reuse a connection for.
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    SYSTEM_ONE_PATH, json=body, headers=self._headers()
                )
        except httpx.TimeoutException as err:
            raise JevApiError(
                "Could not connect to TypeSafe AI. Check your network connection. (timed out)",
                status_code=None,
                retryable=True,
            ) from err
        except httpx.TransportError as err:
            raise JevApiError(
                "Could not connect to TypeSafe AI. Check your network connection.",
                status_code=None,
                retryable=True,
            ) from err

        if response.is_success:
            return _parse_response(response)
        raise _error_for_response(response)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "KilnAI",
        }


def _parse_response(response: httpx.Response) -> SystemOneResponse:
    try:
        payload: Any = response.json()
    except ValueError as err:
        raise RuntimeError(
            "TypeSafe AI returned an unexpected response: invalid JSON"
        ) from err

    try:
        return SystemOneResponse.model_validate(payload)
    except ValidationError as err:
        errors = err.errors()
        detail = str(errors[0]["msg"]) if errors else str(err)
        raise RuntimeError(
            f"TypeSafe AI returned an unexpected response: {detail}"
        ) from err


def _error_for_response(response: httpx.Response) -> JevApiError:
    status = response.status_code
    request_id = response.headers.get(REQUEST_ID_HEADER)
    # Never log the body: it echoes the request's state and questions.
    logger.debug(
        "TypeSafe AI request failed. status=%s request_id=%s", status, request_id
    )

    message, retryable = _message_for_status(response, status)
    return JevApiError(
        message, status_code=status, retryable=retryable, request_id=request_id
    )


def _message_for_status(response: httpx.Response, status: int) -> tuple[str, bool]:
    if status in (401, 403):
        return "Authentication with TypeSafe AI failed. Check your API key.", False
    if status == 429:
        return "TypeSafe AI rate limit exceeded. Wait a moment and try again.", True
    if status == 422:
        return (
            f"TypeSafe AI rejected the request: {_validation_detail(response)}",
            False,
        )
    if 500 <= status < 600:
        return "TypeSafe AI is currently unavailable. Try again in a moment.", True
    return (
        f"TypeSafe AI rejected the request (HTTP {status}): {_truncated_body(response)}",
        False,
    )


def _validation_detail(response: httpx.Response) -> str:
    """The messages from a FastAPI-style validation body, or the raw body if it is not one."""
    try:
        detail = response.json()["detail"]
        messages = [item["msg"] for item in detail]
    except Exception:
        return _truncated_body(response)
    if not messages or not all(isinstance(message, str) for message in messages):
        return _truncated_body(response)
    return "; ".join(messages)


def _truncated_body(response: httpx.Response) -> str:
    return response.text[:MAX_BODY_CHARS_IN_MESSAGE]
