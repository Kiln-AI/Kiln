"""The canonical form of a judged trace for toolset v1.

Every size, offset and search position the tools report is a character position
in a part's canonical text, so this canonicalization is part of the frozen v1
behavior.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from kiln_ai.utils.open_ai_types import TASK_RESPONSE_TOOL_NAME

__all__ = [
    "FILTERABLE_ROLES",
    "PARTS",
    "MessageView",
    "Part",
    "ToolCallRef",
    "TraceView",
    "build_view",
]

Part = Literal["content", "reasoning", "tool_calls"]
"""A part of a message: its text, its reasoning, or the tool calls it made."""
PARTS: tuple[Part, ...] = ("content", "reasoning", "tool_calls")
"""All three parts, in the order part sizes are listed: content, reasoning, tool_calls."""
FILTERABLE_ROLES: tuple[str, ...] = ("system", "developer", "user", "assistant", "tool")
"""The roles the tools can filter by. Other roles are shown but can't be selected."""
UNKNOWN_ROLE = "unknown"
UNKNOWN_TOOL = "unknown tool"
UNKNOWN_CALL_NAME = "unknown"

_JSON_OBJECT_START = re.compile(r"[ \t\n\r]*\{")


@dataclass(frozen=True)
class ToolCallRef:
    """One tool call an assistant message made, other than ``task_response``."""

    name: str
    arguments: str
    """Canonical: valid JSON is re-serialized on one line, unless the result
    can't be encoded as UTF-8; anything else is kept as stored."""
    call_id: str | None
    result_number: int | None
    """The message number of the tool result that answers this call, if any."""


@dataclass(frozen=True)
class MessageView:
    """One message of a judged trace, as the trace tools see it.

    ``content``, ``reasoning`` and ``tool_calls_text`` are the canonical text of
    the message's three parts. Every size and offset the tools report counts
    characters in these strings.
    """

    number: int
    """1-based position in the trace."""
    role: str
    """The stored role, with ``function`` shown as ``tool`` and a missing role as ``unknown``."""
    content: str
    reasoning: str
    tool_calls_text: str
    """One ``name {arguments}`` line per call in ``tool_calls``."""
    tool_calls: tuple[ToolCallRef, ...]
    tool_name: str | None
    """Set on tool results only: the name of the call this result answers."""
    is_error: bool

    def part(self, part: Part) -> str:
        """The canonical text of one part, or an empty string."""
        match part:
            case "content":
                return self.content
            case "reasoning":
                return self.reasoning
            case "tool_calls":
                return self.tool_calls_text

    @property
    def total_chars(self) -> int:
        """The size of all three parts together."""
        return len(self.content) + len(self.reasoning) + len(self.tool_calls_text)

    def non_empty_parts(self) -> tuple[Part, ...]:
        """The parts that have text, in the order content, reasoning, tool_calls."""
        return tuple(part for part in PARTS if self.part(part))


@dataclass(frozen=True)
class TraceView:
    """A judged trace parsed once for the v1 tools. Built by ``build_view``."""

    messages: tuple[MessageView, ...]

    @property
    def count(self) -> int:
        """The number of messages."""
        return len(self.messages)

    def message(self, number: int) -> MessageView:
        """The message with this 1-based number. Callers check the range first."""
        return self.messages[number - 1]

    def part_text(self, number: int, part: Part) -> str:
        """The canonical text of one part of message ``number``."""
        return self.message(number).part(part)


@dataclass(frozen=True)
class _DraftCall:
    name: str
    arguments: str
    call_id: str | None


@dataclass(frozen=True)
class _DraftMessage:
    role: str
    content: str
    reasoning: str
    calls: tuple[_DraftCall, ...]
    tool_call_id: str | None
    legacy_function_name: str | None
    is_error: bool


@dataclass(frozen=True)
class _ResultLinks:
    result_numbers: Mapping[tuple[int, int], int]
    """Keyed by (message number, index in its calls) of each answered call."""
    tool_names: Mapping[int, str]
    """Keyed by the message number of each tool result that answers a call."""


def build_view(trace: Sequence[Mapping[str, Any]]) -> TraceView:
    """Parse a trace (Kiln's OpenAI-style message dicts) into its canonical form.

    Accepts loose dicts and never raises on odd shapes. Runs in time linear in
    the trace size; call it off the event loop for large traces.
    """
    drafts = [_draft_message(raw) for raw in trace]
    links = _link_results(drafts)
    return TraceView(
        messages=tuple(
            _message_view(number, draft, links)
            for number, draft in enumerate(drafts, start=1)
        )
    )


def _link_results(drafts: Sequence[_DraftMessage]) -> _ResultLinks:
    """Pair each tool result with the call it answers, in one pass in trace order.

    A result answers an earlier call with the same id that has no result yet,
    from the latest message that has one, taking that message's calls in order.
    Providers don't keep ids unique: some reuse them on every turn, and some
    give parallel calls in one message the same id.
    """
    unanswered: dict[str, list[tuple[int, int]]] = {}
    result_numbers: dict[tuple[int, int], int] = {}
    tool_names: dict[int, str] = {}
    for number, draft in enumerate(drafts, start=1):
        if draft.role == "tool" and draft.tool_call_id is not None:
            waiting = unanswered.get(draft.tool_call_id)
            if waiting:
                call_number, call_index = waiting.pop()
                result_numbers[(call_number, call_index)] = number
                tool_names[number] = drafts[call_number - 1].calls[call_index].name
        # Pushed last call first, so a message's calls that share an id are
        # answered in call order.
        for call_index in reversed(range(len(draft.calls))):
            call_id = draft.calls[call_index].call_id
            if call_id is not None:
                unanswered.setdefault(call_id, []).append((number, call_index))
    return _ResultLinks(result_numbers=result_numbers, tool_names=tool_names)


def _message_view(
    number: int, draft: _DraftMessage, links: _ResultLinks
) -> MessageView:
    tool_calls = tuple(
        ToolCallRef(
            name=call.name,
            arguments=call.arguments,
            call_id=call.call_id,
            result_number=links.result_numbers.get((number, call_index)),
        )
        for call_index, call in enumerate(draft.calls)
    )
    return MessageView(
        number=number,
        role=draft.role,
        content=draft.content,
        reasoning=draft.reasoning,
        tool_calls_text="\n".join(
            f"{call.name} {call.arguments}" for call in tool_calls
        ),
        tool_calls=tool_calls,
        tool_name=_tool_name(number, draft, links) if draft.role == "tool" else None,
        is_error=draft.is_error,
    )


def _tool_name(number: int, draft: _DraftMessage, links: _ResultLinks) -> str:
    if draft.legacy_function_name is not None:
        return draft.legacy_function_name
    return links.tool_names.get(number, UNKNOWN_TOOL)


def _draft_message(raw: Any) -> _DraftMessage:
    message: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    stored_role = message.get("role")
    role = _view_role(stored_role)
    calls, structured_answer = _calls(message)

    text = _content_text(message.get("content"))
    task_output = _task_tool_output(text) if role == "tool" else None
    pieces = [text if task_output is None else task_output]
    refusal = message.get("refusal")
    if role == "assistant" and isinstance(refusal, str) and refusal:
        pieces.append(f"[refusal] {refusal}")
    if role == "assistant" and structured_answer is not None:
        pieces.append(structured_answer)

    reasoning = message.get("reasoning_content")
    tool_call_id = message.get("tool_call_id")
    legacy_name = message.get("name")
    return _DraftMessage(
        role=role,
        content="\n\n".join(piece for piece in pieces if piece),
        reasoning=reasoning if isinstance(reasoning, str) else "",
        calls=calls,
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) else None,
        legacy_function_name=legacy_name
        if stored_role == "function" and isinstance(legacy_name, str) and legacy_name
        else None,
        is_error=role == "tool" and message.get("is_error") is True,
    )


def _view_role(stored_role: Any) -> str:
    if not isinstance(stored_role, str):
        return UNKNOWN_ROLE
    if stored_role == "function":
        return "tool"
    return stored_role


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        items = (_content_item_text(entry) for entry in content)
        return "\n".join(item for item in items if item is not None)
    return ""


def _content_item_text(entry: Any) -> str | None:
    if not isinstance(entry, Mapping):
        return None
    kind = entry.get("type")
    if not isinstance(kind, str):
        return None
    text = entry.get("text")
    refusal = entry.get("refusal")
    match kind:
        case "text" if isinstance(text, str):
            return text
        case "image_url":
            return "[image]"
        case "input_audio":
            return "[audio]"
        case "file":
            return "[file]"
        case "refusal" if isinstance(refusal, str):
            return f"[refusal] {refusal}"
        case _:
            return f"[{kind}]"


def _task_tool_output(text: str) -> str | None:
    """The task's output, when ``text`` is a Kiln task tool result stored as a
    JSON object whose only key is a string ``output``. Results with other keys
    are kept whole, so no field is hidden from the judge, and so are results
    whose output can't be encoded as UTF-8."""
    if not _JSON_OBJECT_START.match(text):
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if (
        isinstance(parsed, dict)
        and parsed.keys() == {"output"}
        and isinstance(parsed["output"], str)
        and _encodes_as_utf8(parsed["output"])
    ):
        return parsed["output"]
    return None


def _encodes_as_utf8(text: str) -> bool:
    """False if ``text`` holds a lone surrogate. JSON can escape one
    (``"\\ud83d"``), but once decoded it can't be encoded as UTF-8, so a judgment
    quoting it couldn't be saved, and some providers reject it."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _calls(message: Mapping[str, Any]) -> tuple[tuple[_DraftCall, ...], str | None]:
    """The message's tool calls, and the arguments of its last ``task_response``
    call (the structured answer), if any."""
    calls: list[_DraftCall] = []
    structured_answer: str | None = None
    tool_calls = message.get("tool_calls")
    for entry in tool_calls if isinstance(tool_calls, list) else ():
        if not isinstance(entry, Mapping):
            continue
        function = entry.get("function")
        function = function if isinstance(function, Mapping) else {}
        arguments = _canonical_arguments(function)
        if function.get("name") == TASK_RESPONSE_TOOL_NAME:
            structured_answer = arguments
            continue
        call_id = entry.get("id")
        calls.append(
            _DraftCall(
                name=_call_name(function),
                arguments=arguments,
                call_id=call_id if isinstance(call_id, str) else None,
            )
        )

    function_call = message.get("function_call")
    if isinstance(function_call, Mapping):
        calls.append(
            _DraftCall(
                name=_call_name(function_call),
                arguments=_canonical_arguments(function_call),
                call_id=None,
            )
        )
    return tuple(calls), structured_answer


def _call_name(function: Mapping[str, Any]) -> str:
    name = function.get("name")
    return name if isinstance(name, str) and name else UNKNOWN_CALL_NAME


def _canonical_arguments(function: Mapping[str, Any]) -> str:
    if "arguments" not in function:
        return ""
    arguments = function["arguments"]
    if isinstance(arguments, str):
        try:
            canonical = json.dumps(json.loads(arguments), ensure_ascii=False)
        except (ValueError, RecursionError):
            return arguments
        return canonical if _encodes_as_utf8(canonical) else arguments
    try:
        return json.dumps(arguments, ensure_ascii=False, default=str)
    except (ValueError, TypeError, RecursionError):
        return str(arguments)
