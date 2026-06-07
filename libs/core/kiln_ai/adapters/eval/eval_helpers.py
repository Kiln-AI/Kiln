"""Pure-Python helper class injected as the `kiln` argument to user scorer functions.

Stdlib only -- no Pydantic, no Kiln-model/DB/UI imports.
"""

import re
from typing import Any


class KilnEvalHelpers:
    """Utility methods for common scoring patterns in user-authored scorers."""

    # -- Trace navigation --------------------------------------------------

    @staticmethod
    def get_tool_calls(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Return all tool-call entries from a trace (empty list if trace is None)."""
        if not trace:
            return []
        return [
            entry
            for entry in trace
            if entry.get("role") == "tool_call" or entry.get("type") == "tool_call"
        ]

    @staticmethod
    def get_assistant_messages(
        trace: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Return all assistant-role entries from a trace."""
        if not trace:
            return []
        return [entry for entry in trace if entry.get("role") == "assistant"]

    @staticmethod
    def get_tool_results(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Return all tool-result entries from a trace."""
        if not trace:
            return []
        return [
            entry
            for entry in trace
            if entry.get("role") == "tool_result" or entry.get("type") == "tool_result"
        ]

    # -- Tool-call matching -------------------------------------------------

    @staticmethod
    def has_tool_call(
        tool_calls: list[dict[str, Any]],
        tool_name: str,
        expected_args: dict[str, Any] | None = None,
    ) -> bool:
        """Check whether *tool_calls* contains a call to *tool_name*.

        If *expected_args* is provided, the call's arguments must be a
        superset of those key/value pairs.
        """
        for call in tool_calls:
            name = call.get("name") or call.get("tool_name") or ""
            if name != tool_name:
                continue
            if expected_args is None:
                return True
            args = call.get("arguments") or call.get("args") or {}
            if all(args.get(k) == v for k, v in expected_args.items()):
                return True
        return False

    @staticmethod
    def count_tool_calls(
        tool_calls: list[dict[str, Any]],
        tool_name: str | None = None,
    ) -> int:
        """Count tool calls, optionally filtered by *tool_name*."""
        if tool_name is None:
            return len(tool_calls)
        return sum(
            1
            for call in tool_calls
            if (call.get("name") or call.get("tool_name") or "") == tool_name
        )

    # -- Scoring helpers ----------------------------------------------------

    @staticmethod
    def pass_fail(passed: bool) -> float:
        """Return 1.0 for pass, 0.0 for fail."""
        return 1.0 if passed else 0.0

    @staticmethod
    def five_star(rating: int | float) -> float:
        """Return a clamped 1-5 star rating as a float.

        Raises ValueError if *rating* is outside [1, 5].
        """
        if not isinstance(rating, (int, float)) or isinstance(rating, bool):
            raise ValueError(f"rating must be a number, got {type(rating).__name__}")
        if rating < 1 or rating > 5:
            raise ValueError(f"rating must be between 1 and 5, got {rating}")
        return float(rating)

    # -- Assertion helpers --------------------------------------------------

    @staticmethod
    def assert_contains(haystack: str, needle: str) -> bool:
        """Return True if *needle* appears in *haystack*. Never raises."""
        try:
            return needle in haystack
        except Exception:
            return False

    @staticmethod
    def assert_not_contains(haystack: str, needle: str) -> bool:
        """Return True if *needle* does NOT appear in *haystack*. Never raises."""
        try:
            return needle not in haystack
        except Exception:
            return False

    @staticmethod
    def assert_matches(text: str, pattern: str) -> bool:
        """Return True if *pattern* matches anywhere in *text* (re.search). Never raises."""
        try:
            return re.search(pattern, text) is not None
        except Exception:
            return False
