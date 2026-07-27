"""Shared retry classification for LLM-calling pipelines.

AsyncJobRunner retries only jobs that raise RetryableError; pipelines map
provider failures onto that contract through this classifier, so "transient"
means the same thing everywhere a model call can flake (the eval runner,
the synthetic-user batch runner).
"""

import litellm

from kiln_ai.adapters.errors import KilnRunError


def unwrap_kiln_run_error(e: BaseException) -> BaseException:
    """The innermost non-wrapper error.

    The model adapter wraps provider exceptions in KilnRunError (to carry the
    partial trace), whose own message is genericized user-facing text — so both
    retry classification and error detail must use the underlying error. The
    isinstance guard on `original` keeps a (contract-violating) None from
    escaping as the result."""
    while isinstance(e, KilnRunError) and isinstance(e.original, BaseException):
        e = e.original
    return e


def is_retryable_error(e: BaseException) -> bool:
    """True for transient provider failures worth another attempt."""
    e = unwrap_kiln_run_error(e)

    if isinstance(
        e,
        (
            litellm.RateLimitError,
            litellm.APIConnectionError,
            litellm.InternalServerError,
            litellm.ServiceUnavailableError,
            litellm.BadGatewayError,
            litellm.JSONSchemaValidationError,
        ),
    ):
        return True

    # ValueError thrown by Kiln's adapter when structured output doesn't match schema
    if isinstance(
        e, ValueError
    ) and "This task requires a specific output schema" in str(e):
        return True

    return False
