"""The error texts of `call_kiln_api`, returned to the agent as tool errors."""

from collections.abc import Iterable

from kiln_mcp_server.skill_files import API_CATALOGUE_INDEX_PATH


def unknown_endpoint(method: str, path: str) -> str:
    return (
        f"No Kiln API endpoint matches {method} {path}. Do not guess paths. Read "
        f"the API catalogues in the Kiln skill ({API_CATALOGUE_INDEX_PATH}) to find "
        "the endpoint, then read its doc before you call it."
    )


def wrong_method(method: str, path: str, path_methods: Iterable[str]) -> str:
    return (
        f"{method} is not supported on {path}. This path supports: "
        f"{', '.join(path_methods)}. Read the endpoint's doc in the Kiln skill's "
        f"API catalogues ({API_CATALOGUE_INDEX_PATH})."
    )


def blocked_endpoint(method: str, template: str) -> str:
    return (
        f"The endpoint {method} {template} is not available to agents over MCP. "
        "Do not retry it and do not look for another way to call it. If the user "
        "needs this, ask them to do it in the Kiln app."
    )


def body_too_long(length: int, body_limit: int) -> str:
    return (
        f"Body too long. Length {length} on limit {body_limit}. Either narrow your "
        "request (a `jq_filter`, paging or filter parameters), save it to a file "
        "with `save_to_tmpfile`, or call again passing a `body_limit` higher than "
        f"{length}."
    )


def bad_body_limit(body_limit: int) -> str:
    return f"body_limit must be a positive integer. Got: {body_limit}."


def _as_sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else f"{text}."


def request_failed(core_text: str, method: str) -> str:
    """A timeout, a failed connection or another transport failure: the request
    may or may not have run."""
    if method == "GET":
        return core_text
    return (
        f"{_as_sentence(core_text)} The {method} may have taken effect. Check the state before "
        "you repeat it."
    )


def response_unusable(core_text: str, method: str, status_code: int) -> str:
    """The response arrived but is not JSON, or the jq filter failed on it."""
    if method == "GET":
        return core_text
    return (
        f"{_as_sentence(core_text)} The {method} request itself completed with status "
        f"{status_code}. Do not repeat it."
    )


def save_failed(reason: str, method: str, status_code: int) -> str:
    text = (
        f"Could not save the response to a temporary file: {reason}. The request "
        f"completed with status {status_code}."
    )
    if method == "GET":
        return f"{text} Call again without save_to_tmpfile."
    return f"{text} Do not repeat the {method}."


def unexpected_error(error: Exception) -> str:
    return f"Unexpected error in call_kiln_api: {type(error).__name__}: {error}"
