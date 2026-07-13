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
    default_detail: str = "Unknown error.",
) -> T | None:
    """
    Raise an error if the response is not 2xx or a validation error, and return the parsed response.

    The returned value is of the type T.
    """
    check_response_error(response, default_detail=default_detail)

    parsed_response = response.parsed
    # we must check for this to narrow down the type, but this should never
    # happen since check_response_error should raise if it is a validation error
    if isinstance(parsed_response, HTTPValidationError):
        raise RuntimeError("An unknown error occurred.")

    return parsed_response


def unwrap_response(
    response: Response[T | HTTPValidationError],
    default_detail: str = "Unknown error.",
    none_detail: str = "An unknown error occurred.",
) -> T:
    """
    Raise an error if the response is not 2xx or a validation error or None, and return the parsed response.

    If you want to allow None, use unwrap_response_allow_none instead.

    The returned value is of the type T.
    """
    parsed = unwrap_response_allow_none(response, default_detail=default_detail)
    if parsed is None:
        raise HTTPException(status_code=500, detail=none_detail)

    return parsed


def upstream_unreachable(service: str) -> HTTPException:
    """A transport-level failure talking to kiln_server (unreachable host, TLS,
    timeout).

    502, not 500: the failure is in the upstream we proxy to, not in us. Left
    uncaught, httpx's exception escapes and FastAPI reports a bare 500, which
    tells the user nothing about where to look.
    """
    return HTTPException(
        status_code=502,
        detail=(
            f"Couldn't reach the Kiln {service} service. Check your connection, "
            "and that your Kiln server supports it."
        ),
    )


def upstream_route_missing(service: str) -> HTTPException:
    """kiln_server 404'd a request that names no resource — so the route itself
    isn't there (an older deployment, or staging without the feature).

    502, not a propagated 404. Our own 404 must keep meaning "this studio route
    doesn't exist"; passing the upstream 404 straight through sends the user
    hunting for a missing endpoint on the wrong server.

    Only for endpoints that address no resource (e.g. POST /copilot/batch_plan).
    Where the request DOES name a resource (GET /jobs/{id}), a 404 genuinely
    means that resource is missing and must be propagated as-is.
    """
    return HTTPException(
        status_code=502,
        detail=(
            f"This Kiln server doesn't support {service}. It may be an older "
            "deployment — check which Kiln server you're pointed at."
        ),
    )
