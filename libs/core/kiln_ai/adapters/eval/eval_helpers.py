"""Pure-Python helper utilities for user-authored scorer functions.

Users who need these helpers import them explicitly in their scorer code::

    from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

Stdlib only -- no Pydantic, no Kiln-model/DB/UI imports.
"""

import json
import re
from typing import Any

# Inline code spans are removed before link extraction so code like
# `arr[i](x)` doesn't false-positive as a link. [^`]* (not +) lets a pure
# backtick run match in one pass instead of backtracking quadratically.
_MD_CODE_SPAN_RE = re.compile(r"`+[^`]*`+")

# Two-stage parse keeps both regexes linear on adversarial input (these run
# in the sandbox on model output): capture the parenthesized interior with
# one level of nesting, then split target from optional title separately.
_MD_LINK_RE = re.compile(
    r"(?<!!)"  # ![alt](src) is an image, not a link
    r"\[([^\[\]]*)\]"  # link text (nested brackets unsupported)
    r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)"  # interior; one level of parens
)

_MD_TARGET_RE = re.compile(
    r"(\S*)"  # target: no unquoted whitespace
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?"  # optional quoted title, dropped
)


class KilnEvalHelpers:
    """Utility methods for common scoring patterns in user-authored scorers."""

    # -- Trace navigation --------------------------------------------------

    @staticmethod
    def get_tool_calls(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Return all tool calls from a trace as a flat list.

        Each entry is ``{"name": str, "arguments": dict, "id": str | None}``.
        Extracts from OpenAI-format ``role: "assistant"`` messages with nested
        ``tool_calls``.
        """
        if not trace:
            return []
        calls: list[dict[str, Any]] = []
        for msg in trace:
            if msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls") or []:
                func = tc.get("function", {}) if isinstance(tc, dict) else {}
                args_str = func.get("arguments", "{}")
                try:
                    args = (
                        json.loads(args_str) if isinstance(args_str, str) else args_str
                    )
                except (json.JSONDecodeError, TypeError):
                    args = {}
                calls.append(
                    {
                        "name": func.get("name", ""),
                        "arguments": args if isinstance(args, dict) else {},
                        "id": tc.get("id") if isinstance(tc, dict) else None,
                    }
                )
        return calls

    @staticmethod
    def get_assistant_messages(trace: list[dict[str, Any]] | None) -> list[str]:
        """Return the content strings of all assistant messages from a trace.

        Messages whose ``content`` is missing or not a string (e.g. tool-call-only
        assistant turns with ``content: null``) are omitted.
        """
        if not trace:
            return []
        return [
            msg["content"]
            for msg in trace
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), str)
        ]

    @staticmethod
    def get_tool_results(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Return all tool-result entries from a trace.

        Kiln stores traces in OpenAI format, where tool results are
        ``role: "tool"`` messages carrying ``tool_call_id`` and ``content``.
        Entries marked ``role``/``type`` == "tool_result" are also matched,
        defensively, for non-OpenAI-shaped traces.
        """
        if not trace:
            return []
        return [
            entry
            for entry in trace
            if entry.get("role") in ("tool", "tool_result")
            or entry.get("type") == "tool_result"
        ]

    @staticmethod
    def count_messages(trace: list[dict[str, Any]] | None, role: str) -> int:
        """Count trace messages with the given *role* ("user", "assistant",
        "system", or "tool").

        Counts MESSAGES, not tool calls: one assistant message may carry
        several tool calls or none. To count tool calls, use
        ``len(get_tool_calls(trace))`` or ``count_tool_calls``.
        """
        return sum(1 for msg in trace or [] if msg.get("role") == role)

    @staticmethod
    def get_tool_result_content(
        trace: list[dict[str, Any]] | None, tool_call_id: str | None
    ) -> str:
        """Return the text content of the tool result answering *tool_call_id*.

        Pairs OpenAI-format tool results (``role: "tool"``) with their
        originating call by ``tool_call_id``; list-of-blocks content is
        flattened to newline-joined text. Returns ``""`` when *tool_call_id*
        is falsy (``get_tool_calls`` emits ``id: None`` for malformed calls)
        or no result matches. If several results carry the same id, the
        first match wins.
        """
        if not tool_call_id:
            return ""
        for entry in KilnEvalHelpers.get_tool_results(trace):
            if entry.get("tool_call_id") != tool_call_id:
                continue
            content = entry.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # str(... or "") coerces malformed blocks (e.g. text: None)
                # instead of raising from within a user's scorer run.
                return "\n".join(
                    str(block.get("text") or "")
                    if isinstance(block, dict)
                    else str(block)
                    for block in content
                )
            return "" if content is None else str(content)
        return ""

    @staticmethod
    def get_assistant_emitted_text(
        trace: list[dict[str, Any]] | None,
        *,
        include_reasoning: bool = True,
        include_tool_calls: bool = False,
    ) -> str:
        """Text the assistant itself emitted, newline-joined — the surface
        for output-corruption checks.

        Always includes message content (string or text blocks) and refusal
        text; never tool results. Reasoning is included by default
        (*include_reasoning*). Tool-call ARGUMENTS are off by default
        (*include_tool_calls*); tool names are never included — they're
        schema identifiers, not emitted text.

        Caveat: tool-call arguments are JSON-serialized, so non-ASCII text
        may appear as ``\\uXXXX`` escapes — corruption regexes (e.g. CJK
        classes) can mismatch on argument content. That's why arguments
        default to off.
        """
        parts: list[str] = []
        for msg in trace or []:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text") or block.get("content") or ""
                        if isinstance(text, str):
                            parts.append(text)
                    elif isinstance(block, str):
                        parts.append(block)
            refusal = msg.get("refusal")
            if isinstance(refusal, str):
                parts.append(refusal)
            if include_reasoning:
                reasoning = msg.get("reasoning_content") or msg.get("reasoning")
                if isinstance(reasoning, str):
                    parts.append(reasoning)
            if include_tool_calls:
                for tc in msg.get("tool_calls") or []:
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    args = func.get("arguments")
                    if isinstance(args, str):
                        parts.append(args)
        return "\n".join(p for p in parts if p)

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
        """Validate and return a 1-5 star rating as a float.

        Raises ValueError if *rating* is not a number or is outside [1, 5].
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

    # -- Health / usage metrics -----------------------------------------------

    @staticmethod
    def _field(obj: Any, name: str) -> Any:
        """Read *name* from a dict or an attribute-bearing object.

        Trace messages arrive as plain dicts over JSON transports but carry
        Pydantic objects (e.g. ``usage`` as ``MessageUsage``) over the
        in-process pickle transport — duck-type both, no Kiln imports.
        """
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)

    @staticmethod
    def get_usage_totals(trace: list[dict[str, Any]] | None) -> dict[str, float]:
        """Sum per-message ``usage`` across assistant messages.

        Returns ``{"input_tokens", "output_tokens", "total_tokens",
        "cached_tokens", "cost"}`` as floats. Caveat: absent usage data sums
        to 0.0, indistinguishable from a genuine zero — a budget scorer
        silently passes traces whose provider recorded no usage. Check
        ``count_messages(trace, "assistant")`` if you need to tell them
        apart.
        """
        totals = {
            "input_tokens": 0.0,
            "output_tokens": 0.0,
            "total_tokens": 0.0,
            "cached_tokens": 0.0,
            "cost": 0.0,
        }
        for msg in trace or []:
            if msg.get("role") != "assistant":
                continue
            usage = msg.get("usage")
            if usage is None:
                continue
            for key in totals:
                value = KilnEvalHelpers._field(usage, key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    totals[key] += float(value)
        return totals

    @staticmethod
    def get_total_latency_ms(trace: list[dict[str, Any]] | None) -> float:
        """Sum assistant messages' ``latency_ms``; absent values count 0.0.

        Caveat: traces seeded from prior conversations sum across sessions,
        so the total is not one conversation's wall-clock time.
        """
        total = 0.0
        for msg in trace or []:
            if msg.get("role") != "assistant":
                continue
            value = msg.get("latency_ms")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += float(value)
        return total

    @staticmethod
    def get_error_tool_results(
        trace: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Tool results that FLAGGED failure: truthy ``is_error`` or a
        non-empty ``error_message``.

        Caveat: only explicitly flagged errors are caught — a tool that
        returned garbage without setting the flag looks healthy here.
        """
        return [
            entry
            for entry in KilnEvalHelpers.get_tool_results(trace)
            if entry.get("is_error") or entry.get("error_message")
        ]

    # -- Markdown helpers -----------------------------------------------------

    @staticmethod
    def get_markdown_links(text: str | None) -> list[tuple[str, str]]:
        """Return ``(link_text, target)`` pairs for inline markdown links.

        Handles targets with one level of balanced parentheses
        (``.../Foo_(bar)``) and strips optional titles
        (``[t](url "title")``). Images (``![alt](src)``) are excluded and
        inline code spans are ignored. Unsupported (documented subset):
        reference-style links ``[t][ref]``, nested square brackets in link
        text, angle-bracket targets ``[t](<url with spaces>)``, backslash
        escapes, and multi-backtick code spans (handled approximately).
        Never raises; ``None``/empty input yields ``[]``.
        """
        if not text:
            return []
        try:
            without_code = _MD_CODE_SPAN_RE.sub(" ", text)
            links: list[tuple[str, str]] = []
            for link_text, interior in _MD_LINK_RE.findall(without_code):
                target = _MD_TARGET_RE.fullmatch(interior.strip())
                if target is None:
                    # Unquoted whitespace in the target — not a supported link.
                    continue
                links.append((link_text, target.group(1)))
            return links
        except Exception:
            return []
