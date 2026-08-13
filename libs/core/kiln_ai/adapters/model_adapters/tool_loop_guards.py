"""Guards shared by the agent tool-call loops in `litellm_adapter` and `adapter_stream`.

The loops are unbounded: there is no cap on tool calls per turn. A run ends when the
model gives a final answer, when the provider rejects the conversation (e.g. context
window exceeded), or when one of these guards trips. Cost is bounded by the model's
context window and the user's provider account.

Provides:
- `RepeatedToolCallDetector`: warn-then-stop protection against a model looping on
  the same tool call.
- `IncrementalMessageCopier`: keeps the "don't hand litellm our own objects" defense
  while deep-copying each dict message only once. LiteLLM `Message` objects still get
  re-copied every round, so a round that appends one stays O(history), roughly half
  the copying of deep-copying the whole history every round.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable, Sequence

from kiln_ai.adapters.errors import STUCK_LOOP_ERROR_PREFIX
from kiln_ai.utils.open_ai_types import ChatCompletionUserMessageParamWrapper

# A round is "identical" when every tool call in it has the same name, the same
# arguments, and produced the same result as the previous round. Identical results
# carry no new information, so the model cannot make progress by repeating them.
# We nudge once at 3 rounds to give the model a chance to change course, and only
# hard-stop at 5 rounds when the repeated results are errors. Repeated *successful*
# results are never stopped, because legitimate patterns (polling a job that is
# still running) look exactly like that.
STUCK_NUDGE_THRESHOLD = 3
STUCK_STOP_THRESHOLD = 5

# Kiln's internal tool for returning structured output. It ends the turn rather
# than feeding a result back to the model, so it never counts as repetition.
_TASK_RESPONSE_TOOL_NAME = "task_response"

# Stands in for the result text of a failed tool call in a round's fingerprint. Failing
# calls often embed a request id or a timestamp in the error text, which would make every
# retry look like a new round. A retried identical call that keeps failing is the same
# stall whatever the error string says.
_ERROR_RESULT_MARKER = "ERROR"


def _canonical_json(value: Any) -> str:
    """Serialize to a stable string so equal payloads always compare equal."""
    try:
        # default=str stringifies anything JSON can't encode, so two distinct
        # non-serializable values with the same str() compare as equal. Acceptable
        # here: the worst case is one extra round before the streak is noticed.
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        return str(value)


def _canonical_arguments(raw_arguments: Any) -> str:
    """Normalize tool-call arguments so semantically equal calls hash the same.

    Models re-emit the same call with different key order or whitespace, so we parse
    the JSON when we can and fall back to the raw string when we can't.
    """
    if isinstance(raw_arguments, str):
        try:
            return _canonical_json(json.loads(raw_arguments))
        except (json.JSONDecodeError, TypeError):
            return raw_arguments
    return _canonical_json(raw_arguments)


def _result_digest(content: Any) -> str:
    """Hash the tool result so we compare rounds without retaining large payloads."""
    text = content if isinstance(content, str) else _canonical_json(content)
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


class RepeatedToolCallDetector:
    """Tracks consecutive rounds of identical tool calls within one model turn.

    Call `record_round` once per tool-call round. It returns a nudge message to append
    to the conversation (or None), and raises `RuntimeError` when a failing loop should
    be stopped. Any change in the tool set, arguments, or results resets the streak.
    """

    def __init__(self) -> None:
        self._fingerprint: tuple[tuple[str, str, str], ...] | None = None
        self._count = 0
        self._nudged = False

    def record_round(
        self,
        tool_calls: Iterable[Any] | None,
        tool_messages: Sequence[Any],
    ) -> ChatCompletionUserMessageParamWrapper | None:
        """Record one tool-call round; return a nudge message to append, or None.

        `tool_calls` are the model's requested calls (LiteLLM tool call objects) and
        `tool_messages` the resulting role="tool" messages, matched by tool_call_id.
        """
        fingerprint, tool_names, round_is_all_errors = self._describe_round(
            tool_calls, tool_messages
        )

        # A round with no real tool calls (e.g. task_response only) breaks any streak.
        if not fingerprint:
            self._reset()
            return None

        if fingerprint != self._fingerprint:
            self._fingerprint = fingerprint
            self._count = 1
            self._nudged = False
            return None

        self._count += 1

        if self._count >= STUCK_STOP_THRESHOLD and round_is_all_errors:
            raise RuntimeError(
                f"{STUCK_LOOP_ERROR_PREFIX}. It called {tool_names} with the same "
                f"arguments {self._count} times in a row and got the same error each "
                "time, including after being asked to change approach."
            )

        if self._count >= STUCK_NUDGE_THRESHOLD and not self._nudged:
            self._nudged = True
            # A plain user message so every provider surfaces it to the model.
            # `kiln_injected` marks it as ours: stripped before the provider call, kept
            # in the trace so the run can tell it apart from real user input.
            return ChatCompletionUserMessageParamWrapper(
                role="user",
                content=(
                    f"You have called {tool_names} with the same arguments "
                    f"{self._count} times and received the same result each time. "
                    "Repeating the identical call will not work. Change your approach "
                    "or provide your final answer."
                ),
                kiln_injected=True,
            )

        return None

    def _reset(self) -> None:
        self._fingerprint = None
        self._count = 0
        self._nudged = False

    @staticmethod
    def _describe_round(
        tool_calls: Iterable[Any] | None,
        tool_messages: Sequence[Any],
    ) -> tuple[tuple[tuple[str, str, str], ...], str, bool]:
        """Return (round fingerprint, human-readable tool names, every-result-failed)."""
        results_by_id: dict[str, Any] = {}
        errors_by_id: dict[str, bool] = {}
        for message in tool_messages:
            if not isinstance(message, dict):
                continue
            call_id = message.get("tool_call_id")
            if call_id is None:
                continue
            results_by_id[call_id] = message.get("content")
            # `is_error` is the only reliable error signal available here: tools set it
            # on ToolCallResult (MCP maps CallToolResult.isError onto it) and the adapter
            # copies it onto the tool message. Tools without it are treated as success.
            errors_by_id[call_id] = bool(message.get("is_error"))

        entries: list[tuple[str, str, str]] = []
        names: list[str] = []
        error_flags: list[bool] = []
        for tool_call in tool_calls or []:
            function = getattr(tool_call, "function", None)
            name = getattr(function, "name", None) or "unknown"
            if name == _TASK_RESPONSE_TOOL_NAME:
                continue
            call_id = getattr(tool_call, "id", None)
            if call_id not in results_by_id:
                # No matching result (e.g. the caller handles this tool). Nothing to
                # compare, so don't treat the round as repeatable.
                continue
            arguments = _canonical_arguments(getattr(function, "arguments", None))
            is_error = errors_by_id.get(call_id, False)
            # Failed calls compare by a constant marker rather than by their error text,
            # so a call that keeps failing with a different message each time is still
            # recognized as the same stall. Successful results compare by content.
            result = (
                _ERROR_RESULT_MARKER
                if is_error
                else _result_digest(results_by_id[call_id])
            )
            entries.append((name, arguments, result))
            names.append(name)
            error_flags.append(is_error)

        # Only stop when every result in this round is an error. A mixed round still
        # makes progress on the succeeding call, so it gets the nudge and nothing more.
        round_is_all_errors = bool(error_flags) and all(error_flags)
        return (
            tuple(sorted(entries)),
            ", ".join(dict.fromkeys(names)),
            round_is_all_errors,
        )


# Value types that can't hold a nested mutation. A dict message whose values are all
# of these has no shared state to protect beyond the dict itself.
_IMMUTABLE_VALUE_TYPES = (str, int, float, bool, type(None))


def _needs_per_round_copy(message: Any) -> bool:
    """True if reusing this cached message could carry a mutation into the next round."""
    if not isinstance(message, dict):
        # LiteLLM Message objects reach the provider untouched (sanitize only rebuilds
        # dicts), so the provider holds our object and each round needs its own.
        return True
    # sanitize rebuilds the top level of every dict before the provider call, but that
    # copy is shallow: nested containers stay shared, so re-copy dicts that hold them.
    return not all(
        isinstance(value, _IMMUTABLE_VALUE_TYPES) for value in message.values()
    )


class IncrementalMessageCopier:
    """Hands each round of a tool loop its own copy of a growing message history.

    litellm mutates the message objects it is handed, so the adapters never pass their
    canonical list. Deep-copying the whole history every round made a long tool loop
    quadratic; this deep-copies each message once, when it first appears, into a master
    it keeps.

    Exact reuse semantics of `snapshot()`:
    - The caller's own objects are never handed out, and the returned list is new each
      round.
    - Entries that could carry a mutation forward are re-copied every round: LiteLLM
      `Message` objects (the provider receives these as-is) and dict messages holding
      nested containers (`sanitize_messages_for_provider` copies dicts only one level
      deep). A mutation of one round's snapshot cannot reach the next round's.
    - Flat dict messages (every value a string, number, bool or None) are handed back
      by reference, so they cost nothing after the round that added them. A round that
      appends a `Message` still re-copies every `Message` in the history, so the loop
      stays linear per round rather than dropping to O(new). Handing flat dicts back is
      safe because sanitize rebuilds each dict, so the provider never receives one of
      ours, and there is no nested value for it to reach. Callers must not mutate a
      snapshot's dicts in place.
    """

    def __init__(self) -> None:
        self._sources: list[Any] = []
        self._master: list[Any] = []

    def snapshot(self, messages: Sequence[Any]) -> list[Any]:
        """Return a copy of `messages`, reusing deep copies made on earlier calls."""
        if not self._prefix_matches(messages):
            # The history was rewritten rather than appended to, so our copies are
            # stale and everything has to be copied again.
            self._sources = list(messages)
            self._master = copy.deepcopy(list(messages))
        else:
            new_messages = list(messages[len(self._master) :])
            if new_messages:
                self._sources.extend(new_messages)
                self._master.extend(copy.deepcopy(new_messages))

        return [
            copy.deepcopy(message) if _needs_per_round_copy(message) else message
            for message in self._master
        ]

    def _prefix_matches(self, messages: Sequence[Any]) -> bool:
        """True if `messages` still starts with the exact objects we already copied.

        Identity, not equality: a caller that mutates an already-appended source message
        in place keeps the same object, so this still matches and the stale copy in the
        master gets reused. Callers must append to the history, never edit it in place.
        """
        if len(messages) < len(self._master):
            return False
        return all(messages[i] is source for i, source in enumerate(self._sources))
