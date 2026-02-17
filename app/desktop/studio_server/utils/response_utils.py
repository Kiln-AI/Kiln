import json

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    HTTPValidationError,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import Response
from fastapi import HTTPException
from typing_extensions import TypeVar


def check_response_error(
    response: Response, default_detail: str = "Unknown error."
) -> None:
    """Check if the response is an error with user centric message."""
    if not (200 <= response.status_code < 300):
        # response.content is a bytes object
        # We check if it's a JSON object with a user message field
        detail = default_detail
        if response.content.startswith(b"{"):
            try:
                json_data = json.loads(response.content)
                detail = json_data.get("message", default_detail)
            except json.JSONDecodeError:
                pass
        raise HTTPException(
            status_code=response.status_code,
            detail=detail,
        )


T = TypeVar("T")


def unwrap_response_allow_none(
    response: Response[T | HTTPValidationError],
) -> T | None:
    """
    Raise an error if the response is not 2xx or a validation error, and return the parsed response.

    The returned value is of the type T.
    """
    check_response_error(response)

    parsed_response = response.parsed
    # we must check for this to narrow down the type, but this should never
    # happen since check_response_error should raise if it is a validation error
    if isinstance(parsed_response, HTTPValidationError):
        raise RuntimeError("An unknown error occurred.")

    return parsed_response


def unwrap_response(response: Response[T | HTTPValidationError]) -> T:
    """
    Raise an error if the response is not 2xx or a validation error or None, and return the parsed response.

    If you want to allow None, use unwrap_response_allow_none instead.

    The returned value is of the type T.
    """
    parsed = unwrap_response_allow_none(response)
    if parsed is None:
        raise RuntimeError("An unknown error occurred.")

    return parsed
