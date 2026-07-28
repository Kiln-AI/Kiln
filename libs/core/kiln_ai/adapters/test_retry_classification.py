import httpx
import litellm
import pytest

from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.retry_classification import (
    is_batch_fatal_error,
    is_retryable_error,
)


def _provider_error(cls, message: str = "boom"):
    """litellm exception constructors want provider context (and some, like
    PermissionDeniedError, a raw response)."""
    try:
        return cls(message=message, llm_provider="openrouter", model="gpt_5_5")
    except TypeError:
        response = httpx.Response(
            status_code=403, request=httpx.Request("POST", "http://test")
        )
        return cls(
            message=message,
            llm_provider="openrouter",
            model="gpt_5_5",
            response=response,
        )


def _wrapped(error: Exception) -> KilnRunError:
    return KilnRunError("generic user-facing text", partial_trace=None, original=error)


class TestIsBatchFatalError:
    @pytest.mark.parametrize(
        "cls",
        [
            litellm.AuthenticationError,
            litellm.PermissionDeniedError,
            litellm.NotFoundError,
        ],
    )
    def test_config_scoped_provider_errors_are_batch_fatal(self, cls):
        assert is_batch_fatal_error(_provider_error(cls)) is True

    def test_budget_exceeded_is_batch_fatal(self):
        error = litellm.BudgetExceededError(current_cost=2.0, max_budget=1.0)
        assert is_batch_fatal_error(error) is True

    @pytest.mark.parametrize(
        "error",
        [
            # Transient classes must stay case-scoped (and retryable).
            _provider_error(litellm.RateLimitError),
            _provider_error(litellm.InternalServerError),
            _provider_error(litellm.ServiceUnavailableError),
            # Unrecognized errors must never abort a batch on a guess.
            ValueError("some judge parsing problem"),
            RuntimeError("anything else"),
            TimeoutError("slow provider"),
        ],
    )
    def test_everything_else_stays_case_scoped(self, error):
        assert is_batch_fatal_error(error) is False

    def test_unwraps_kiln_run_error(self):
        inner = _provider_error(litellm.AuthenticationError)
        assert is_batch_fatal_error(_wrapped(inner)) is True

    def test_batch_fatal_is_disjoint_from_retryable(self):
        # The abort path assumes a batch-fatal error is deterministic — a
        # class in both sets would retry twice and then abort, wasting the
        # retries and delaying the abort.
        for cls in (
            litellm.AuthenticationError,
            litellm.PermissionDeniedError,
            litellm.NotFoundError,
        ):
            error = _provider_error(cls)
            assert is_retryable_error(error) is False
            assert is_batch_fatal_error(error) is True


class TestUnwrapInteraction:
    def test_wrapped_transient_is_retryable_not_fatal(self):
        wrapped = _wrapped(_provider_error(litellm.RateLimitError))
        assert is_retryable_error(wrapped) is True
        assert is_batch_fatal_error(wrapped) is False
