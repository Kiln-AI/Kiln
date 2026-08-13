"""Shared error types for adapter runs.

Provides:
- `ErrorWithTrace`: the API response body for run failures.
- `KilnRunError`: the exception thrown by the adapter that carries the partial
  conversation trace across the exception boundary so the API layer can return
  it to the client.
- `format_error_message`: maps known exceptions to user-friendly text.
"""

from __future__ import annotations

import litellm
from pydantic import BaseModel

from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

_GENERIC_FALLBACK_MESSAGE = "An unexpected error occurred."

# Stable prefix the agent tool loops raise with when they stop a stuck model. Lives
# here (not with the loops) so the raise side and this mapping can't drift apart.
STUCK_LOOP_ERROR_PREFIX = "Model is stuck repeating the same failing tool call"


class ErrorWithTrace(BaseModel):
    """Structured error response pairing a user-friendly message with the
    partial conversation trace built up before the failure.

    Returned by endpoints that run a task adapter when the adapter throws
    after starting a run (LLM calls made, tools invoked, etc.).
    """

    message: str
    error_type: str
    trace: list[ChatCompletionMessageParam] | None = None


class KilnRunError(Exception):
    """Raised when an adapter run fails after the trace has started being built.

    Carries the partial trace so the API layer can return it to the client.
    The original exception chain is preserved via `__cause__`.
    """

    def __init__(
        self,
        message: str,
        partial_trace: list[ChatCompletionMessageParam] | None,
        original: Exception,
    ) -> None:
        super().__init__(message)
        self.partial_trace = partial_trace
        self.original = original
        self.error_type = type(original).__name__


def _safe_str(exc: Exception) -> str:
    """Return str(exc); fall back to the exception class name if the string
    is empty, and to a generic message only if str() itself misbehaves."""
    try:
        result = str(exc)
    except Exception:
        return _GENERIC_FALLBACK_MESSAGE
    if not isinstance(result, str):
        return _GENERIC_FALLBACK_MESSAGE
    if not result:
        # An exception with an empty __str__ (e.g., RuntimeError("")) is more
        # useful to the user as the class name than a generic fallback.
        return type(exc).__name__
    return result


def format_error_message(exc: Exception) -> str:
    """Map an exception to a user-friendly message.

    Known exception types get custom messages. Unknown types get a generic
    fallback to avoid leaking provider internals to the client.
    """
    try:
        # Order matters: several litellm error classes inherit from each
        # other (e.g., RateLimitError is a subclass of InternalServerError in
        # some litellm versions), so we match the most specific types first
        # and fall through to the broader "provider unavailable" bucket last.
        if isinstance(exc, litellm.RateLimitError):
            return "Rate limit exceeded. Wait a moment and try again."
        if isinstance(exc, litellm.AuthenticationError):
            return "Authentication with the model provider failed. Check your API key."
        if isinstance(exc, litellm.APIConnectionError):
            return "Could not connect to the model provider. Check your network connection."
        if isinstance(
            exc,
            (
                litellm.ServiceUnavailableError,
                litellm.BadGatewayError,
                litellm.InternalServerError,
            ),
        ):
            return "The model provider is currently unavailable. Try again in a moment."
        if isinstance(exc, litellm.JSONSchemaValidationError):
            return "The model's output didn't match the expected format."
        # Must be checked before the generic BadRequestError below, since
        # ContextWindowExceededError is a subclass of it.
        if isinstance(exc, litellm.ContextWindowExceededError):
            return (
                "The run exceeded the model's context window. The conversation, "
                "including tool calls and results, grew too large for this model. "
                + _safe_str(exc)
            )
        # Also a BadRequestError subclass, so it must be checked before the generic
        # branch. Providers return this when a safety classifier blocks the request.
        if isinstance(exc, litellm.ContentPolicyViolationError):
            return (
                "The model provider's safety filter blocked this request. This can be a "
                "false positive on some models. Try rephrasing the prompt or using a "
                "different model. " + _safe_str(exc)
            )
        # Everything above is either a more specific BadRequestError subclass or a
        # different status code entirely, so this can't shadow them. Unmapped 400s
        # (including context overflows litellm didn't recognize) are more useful with
        # the provider's own detail than with the generic fallback.
        if isinstance(exc, litellm.BadRequestError):
            return "The model provider rejected the request. " + _safe_str(exc)

        if isinstance(exc, RuntimeError):
            msg = _safe_str(exc)
            if msg.startswith("Too many turns"):
                return "The run exceeded the maximum number of turns."
            if msg.startswith(STUCK_LOOP_ERROR_PREFIX):
                return (
                    "The run was stopped because the model kept repeating the same "
                    "failing tool call after being warned. The run trace shows the "
                    "repeated calls and the warning."
                )
            # Other RuntimeErrors (tool not found, arg parse/validate failures,
            # reasoning required) already have user-friendly messages with
            # useful context (e.g., tool names), so pass them through.
            return msg

        if isinstance(exc, ValueError):
            # ValueError messages from the adapter (schema mismatches, etc.)
            # are already user-readable and include helpful detail.
            return _safe_str(exc)

        return _GENERIC_FALLBACK_MESSAGE
    except Exception:
        return _GENERIC_FALLBACK_MESSAGE
