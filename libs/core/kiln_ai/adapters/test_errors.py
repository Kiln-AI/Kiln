"""Tests for kiln_ai.adapters.errors."""

from __future__ import annotations

import httpx
import litellm
import pytest

from kiln_ai.adapters.errors import (
    ErrorWithTrace,
    KilnRunError,
    format_error_message,
)


def _make_litellm_error(cls, *, message: str = "boom"):
    """Construct a litellm error instance with minimal required fields.

    litellm error classes require (message, model, llm_provider) plus some
    require response/body. Use a fake httpx.Response where needed.
    """
    common_kwargs = {
        "message": message,
        "model": "test-model",
        "llm_provider": "openai",
    }
    try:
        return cls(**common_kwargs)
    except TypeError:
        # Some subclasses (e.g., APIConnectionError) need a `request`; others
        # need `response` or `body`. Try a few shapes.
        pass

    try:
        return cls(
            message=message,
            llm_provider="openai",
            model="test-model",
            response=httpx.Response(500, request=httpx.Request("POST", "http://x")),
        )
    except TypeError:
        pass

    try:
        return cls(
            message=message,
            llm_provider="openai",
            model="test-model",
            request=httpx.Request("POST", "http://x"),
        )
    except TypeError:
        pass

    # Last resort: pass message positionally
    return cls(message)


class TestFormatUserMessage:
    def test_rate_limit_error(self):
        exc = _make_litellm_error(litellm.RateLimitError)
        assert (
            format_error_message(exc)
            == "Rate limit exceeded. Wait a moment and try again."
        )

    def test_authentication_error(self):
        exc = _make_litellm_error(litellm.AuthenticationError)
        assert (
            format_error_message(exc)
            == "Authentication with the model provider failed. Check your API key."
        )

    def test_api_connection_error(self):
        exc = _make_litellm_error(litellm.APIConnectionError)
        assert (
            format_error_message(exc)
            == "Could not connect to the model provider. Check your network connection."
        )

    @pytest.mark.parametrize(
        "cls",
        [
            litellm.ServiceUnavailableError,
            litellm.BadGatewayError,
            litellm.InternalServerError,
        ],
    )
    def test_service_unavailable_family(self, cls):
        exc = _make_litellm_error(cls)
        assert (
            format_error_message(exc)
            == "The model provider is currently unavailable. Try again in a moment."
        )

    def test_json_schema_validation_error(self):
        # JSONSchemaValidationError has a different constructor
        try:
            exc = litellm.JSONSchemaValidationError(
                model="test-model",
                llm_provider="openai",
                raw_response="{}",
                schema="{}",
            )
        except TypeError:
            # fall back to a bare instance
            exc = litellm.JSONSchemaValidationError.__new__(
                litellm.JSONSchemaValidationError
            )
            Exception.__init__(exc, "schema mismatch")
        assert (
            format_error_message(exc)
            == "The model's output didn't match the expected format."
        )

    def test_too_many_turns(self):
        exc = RuntimeError(
            "Too many turns (11). Stopping iteration to avoid using too many tokens."
        )
        assert (
            format_error_message(exc) == "The run exceeded the maximum number of turns."
        )

    def test_too_many_tool_calls(self):
        exc = RuntimeError(
            "Too many tool calls (31). Stopping iteration to avoid using too many tokens."
        )
        assert (
            format_error_message(exc)
            == "The run exceeded the maximum number of tool calls in one turn."
        )

    def test_tool_not_available(self):
        exc = RuntimeError(
            "A tool named 'foo' was invoked by a model, but was not available."
        )
        assert (
            format_error_message(exc)
            == "The model tried to call a tool that isn't available on this task."
        )

    def test_parse_arguments(self):
        exc = RuntimeError(
            "Failed to parse arguments for tool 'foo' (should be JSON): blah"
        )
        assert (
            format_error_message(exc)
            == "The model produced invalid arguments for a tool call."
        )

    def test_validate_arguments(self):
        exc = RuntimeError(
            "Failed to validate arguments for tool 'foo'. The arguments didn't match..."
        )
        assert (
            format_error_message(exc)
            == "The model's tool call arguments didn't match the tool's schema."
        )

    def test_reasoning_required(self):
        exc = RuntimeError(
            "Reasoning is required for this model, but no reasoning was returned."
        )
        assert (
            format_error_message(exc)
            == "The model should have returned reasoning but didn't."
        )

    def test_schema_mismatch_value_error(self):
        exc = ValueError(
            "This task requires a specific output schema. While the model produced JSON, "
            "that JSON didn't meet the schema. Search 'Troubleshooting Structured Data Issues' in our docs for more information."
        )
        assert (
            format_error_message(exc)
            == "The model's output didn't match the task's output schema."
        )

    def test_unknown_exception_uses_generic_message(self):
        exc = KeyError("missing_key")
        assert format_error_message(exc) == "An unexpected error occurred."

    def test_unknown_exception_type_uses_generic_message(self):
        class WeirdError(Exception):
            pass

        exc = WeirdError("something odd")
        assert format_error_message(exc) == "An unexpected error occurred."

    def test_runtime_error_without_known_prefix_uses_generic_message(self):
        exc = RuntimeError("something random happened")
        assert format_error_message(exc) == "An unexpected error occurred."

    def test_value_error_without_schema_hint_uses_generic_message(self):
        exc = ValueError("just a regular value error")
        assert format_error_message(exc) == "An unexpected error occurred."

    def test_survives_broken_str(self):
        class BrokenStrError(Exception):
            def __str__(self):
                raise RuntimeError("str is broken")

        exc = BrokenStrError("hidden")
        # Should not raise; should return the generic fallback.
        assert format_error_message(exc) == "An unexpected error occurred."

    def test_empty_message_falls_back_to_generic(self):
        exc = RuntimeError("")
        assert format_error_message(exc) == "An unexpected error occurred."

    def test_empty_message_custom_class_uses_generic(self):
        class WeirdError(Exception):
            pass

        exc = WeirdError("")
        assert format_error_message(exc) == "An unexpected error occurred."


class TestKilnRunError:
    def test_attributes_preserved(self):
        original = RuntimeError("underlying")
        partial_trace = [{"role": "user", "content": "hi"}]
        err = KilnRunError(
            message="friendly",
            partial_trace=partial_trace,  # type: ignore[arg-type]
            original=original,
        )
        assert str(err) == "friendly"
        assert err.partial_trace is partial_trace
        assert err.original is original
        assert err.error_type == "RuntimeError"

    def test_error_type_uses_class_name(self):
        original = ValueError("x")
        err = KilnRunError(message="m", partial_trace=None, original=original)
        assert err.error_type == "ValueError"

    def test_cause_chain_preserved(self):
        original = RuntimeError("underlying")
        try:
            try:
                raise original
            except Exception as e:
                raise KilnRunError(message="m", partial_trace=None, original=e) from e
        except KilnRunError as err:
            assert err.__cause__ is original

    def test_accepts_none_partial_trace(self):
        err = KilnRunError(message="m", partial_trace=None, original=RuntimeError("x"))
        assert err.partial_trace is None


class TestErrorWithTrace:
    def test_serializes_with_none_trace(self):
        err = ErrorWithTrace(message="nope", error_type="RuntimeError", trace=None)
        dumped = err.model_dump()
        assert dumped == {
            "message": "nope",
            "error_type": "RuntimeError",
            "trace": None,
        }
        assert ErrorWithTrace.model_validate(dumped) == err

    def test_serializes_with_empty_trace(self):
        err = ErrorWithTrace(message="nope", error_type="RuntimeError", trace=[])
        dumped = err.model_dump()
        assert dumped["trace"] == []
        assert ErrorWithTrace.model_validate(dumped) == err

    def test_serializes_with_populated_trace(self):
        trace = [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hi"},
        ]
        err = ErrorWithTrace(
            message="boom",
            error_type="RateLimitError",
            trace=trace,  # type: ignore[arg-type]
        )
        dumped = err.model_dump()
        assert dumped["trace"] == trace
        rehydrated = ErrorWithTrace.model_validate(dumped)
        assert rehydrated.message == "boom"
        assert rehydrated.error_type == "RateLimitError"
        assert rehydrated.trace == trace

    def test_trace_defaults_to_none(self):
        err = ErrorWithTrace(message="m", error_type="E")
        assert err.trace is None
