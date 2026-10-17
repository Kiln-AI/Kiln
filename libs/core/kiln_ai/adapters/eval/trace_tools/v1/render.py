"""Text output of the v1 trace tools, except search.

Pure functions over a ``TraceView``. Bad arguments and oversized responses raise
``TraceToolUsageError``.
"""

import heapq
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.limits import (
    NAME_CHARS,
    OVERVIEW_LARGEST,
    OVERVIEW_OTHER_ROLES,
    OVERVIEW_PREVIEW_CHARS,
    OVERVIEW_TOP_TOOLS,
    PREVIEW_CHARS_DEFAULT,
    READ_MAX_CHARS_DEFAULT,
    RESPONSE_CHARS,
    TEXT_MAX_CHARS_DEFAULT,
)
from kiln_ai.adapters.eval.trace_tools.v1.view import (
    FILTERABLE_ROLES,
    PARTS,
    MessageView,
    Part,
    ToolCallRef,
    TraceView,
)

__all__ = [
    "PreviewArgs",
    "ReadArgs",
    "TextArgs",
    "preview_messages",
    "read_message_text",
    "read_messages",
    "render_overview",
]

EN_DASH = "\u2013"
EM_DASH = "\u2014"
TIMES = "\u00d7"
MIDDLE_DOT = "\u00b7"
ARROW = "\u2192"
ELLIPSIS = "\u2026"

DEFAULT_PARTS: tuple[Part, ...] = ("content", "tool_calls")
BODY_PART_ORDER: tuple[Part, ...] = ("reasoning", "content", "tool_calls")

_PREVIEW_ADVICE = "use a smaller start/end range, a roles filter, or preview_chars=0"
_READ_ADVICE = (
    "use a smaller range or fewer numbers, a roles filter, fewer parts, or a lower "
    "max_chars; or call preview_messages first to choose messages"
)


@dataclass(frozen=True)
class PreviewArgs:
    """Arguments of ``preview_messages``, with defaults applied."""

    start: int | None = None
    """None means the first message."""
    end: int | None = None
    """None means the last message."""
    roles: tuple[str, ...] | None = None
    preview_chars: int = PREVIEW_CHARS_DEFAULT


@dataclass(frozen=True)
class ReadArgs:
    """Arguments of ``read_messages``, with defaults applied. Give ``numbers`` or
    ``start``/``end``, not both."""

    numbers: tuple[int, ...] | None = None
    start: int | None = None
    end: int | None = None
    roles: tuple[str, ...] | None = None
    parts: tuple[Part, ...] = DEFAULT_PARTS
    max_chars: int = READ_MAX_CHARS_DEFAULT


@dataclass(frozen=True)
class TextArgs:
    """Arguments of ``read_message_text``, with defaults applied."""

    number: int
    part: Part = "content"
    offset: int = 0
    max_chars: int = TEXT_MAX_CHARS_DEFAULT


def fmt_number(value: int) -> str:
    return f"{value:,}"


def fmt_count(value: int, word: str, plural: str | None = None) -> str:
    noun = word if value == 1 else (plural or f"{word}s")
    return f"{fmt_number(value)} {noun}"


def approx_tokens(chars: int) -> str:
    tokens = chars / 4
    if tokens < 1_000:
        return f"~{round(tokens)}"
    if tokens < 1_000_000:
        return f"~{round(tokens / 1_000)}k"
    return f"~{tokens / 1_000_000:.1f}M"


def quote(text: str, max_chars: int) -> str:
    quoted = json.dumps(text[:max_chars], ensure_ascii=False)
    return f"{quoted} <truncated>" if len(text) > max_chars else quoted


def display_name(name: str) -> str:
    """A role or tool name as shown in labels: names from the trace can be any
    length, so long ones are cut."""
    if len(name) <= NAME_CHARS:
        return name
    return f"{name[:NAME_CHARS]}{ELLIPSIS}"


def short_label(message: MessageView) -> str:
    if message.tool_name is not None:
        return f"tool {display_name(message.tool_name)}"
    return display_name(message.role)


def long_label(message: MessageView) -> str:
    if message.tool_name is not None:
        return f"tool result from {display_name(message.tool_name)}"
    return display_name(message.role)


def roles_suffix(roles: Sequence[str] | None) -> str:
    return f", roles: {', '.join(roles)}" if roles else ""


def continuation_marker(remaining: int, number: int, part: Part, offset: int) -> str:
    return (
        f"<truncated: {fmt_number(remaining)} more chars; "
        f"read_message_text(number={number}, part={part}, offset={offset})>"
    )


def check_message_number(view: TraceView, number: int) -> None:
    if 1 <= number <= view.count:
        return
    if view.count == 0:
        raise TraceToolUsageError("The trace has no messages.")
    raise TraceToolUsageError(
        f"Message #{number} doesn't exist. The trace has "
        f"{fmt_count(view.count, 'message')} (#1{EN_DASH}#{view.count})."
    )


def resolve_range(
    view: TraceView, start: int | None, end: int | None
) -> tuple[int, int]:
    """The inclusive message range, with start defaulting to 1 and end to the last message."""
    first = 1 if start is None else start
    last = view.count if end is None else end
    check_message_number(view, first)
    check_message_number(view, last)
    if first > last:
        raise TraceToolUsageError(f"start ({first}) is after end ({last}).")
    return first, last


def check_filters(roles: Iterable[str] | None, parts: Iterable[str] | None) -> None:
    _check_values("role", roles, FILTERABLE_ROLES)
    _check_values("part", parts, PARTS)


def _check_values(
    kind: str, values: Iterable[str] | None, valid: Sequence[str]
) -> None:
    for value in values or ():
        if value not in valid:
            raise unknown_value_error(kind, value, valid)


def unknown_value_error(
    kind: str, value: object, valid: Sequence[str]
) -> TraceToolUsageError:
    return TraceToolUsageError(
        f'Unknown {kind} "{value}". Valid {kind}s: {", ".join(valid)}.'
    )


def check_numbers_or_range(
    numbers: Sequence[int] | None, start: int | None, end: int | None
) -> None:
    if numbers is not None and (start is not None or end is not None):
        raise TraceToolUsageError("Use either numbers or start/end, not both.")


def role_selected(message: MessageView, roles: Sequence[str] | None) -> bool:
    return roles is None or message.role in roles


@dataclass(frozen=True)
class Unit:
    """One line or block of a response, from one message."""

    message_number: int
    text: str


FitStyle = Literal["range", "numbers", "matches"]


@dataclass(frozen=True)
class RefusalContext:
    style: FitStyle
    advice: str
    fit_footer: str | None = None
    """The footer a narrowed request would end with, when it can be longer than
    this response's footer. The fit is computed with it, so the narrowed
    request is sure to fit."""


def assemble(
    units: Sequence[Unit],
    header: str | None,
    footer: str | None,
    refusal: RefusalContext,
) -> str:
    """Join the response, or raise a refusal naming what fits if it is over the limit."""
    lines = _lines(header, [unit.text for unit in units], footer)
    size = _joined_size(lines)
    if size <= RESPONSE_CHARS:
        return "\n".join(lines)

    fit_footer = refusal.fit_footer if refusal.fit_footer is not None else footer
    fitting = _fitting_unit_count(units, header, fit_footer)
    raise TraceToolUsageError(
        f"Too large: this would return {fmt_number(size)} chars, over the "
        f"{fmt_number(RESPONSE_CHARS)} limit. Nothing was returned.\n"
        f"{_fit_line(refusal.style, units, fitting)}\n"
        f"To narrow it: {refusal.advice}."
    )


def _lines(header: str | None, texts: list[str], footer: str | None) -> list[str]:
    return (
        ([header] if header is not None else [])
        + texts
        + ([footer] if footer is not None else [])
    )


def _joined_size(lines: Sequence[str]) -> int:
    return sum(len(line) for line in lines) + max(0, len(lines) - 1)


def _fitting_unit_count(
    units: Sequence[Unit], header: str | None, footer: str | None
) -> int:
    fixed = _lines(header, [], footer)
    size = _joined_size(fixed)
    line_count = len(fixed)
    fitting = 0
    for unit in units:
        size += len(unit.text) + (1 if line_count > 0 else 0)
        line_count += 1
        if size > RESPONSE_CHARS:
            break
        fitting += 1
    return fitting


def _fit_line(style: FitStyle, units: Sequence[Unit], fitting: int) -> str:
    if style == "matches":
        if fitting == 0:
            return "Even one match is too large at these settings."
        return f"count={fitting} fits at these settings."

    first = units[0].message_number
    if fitting == 0:
        return (
            f"Even #{first} alone is {fmt_number(len(units[0].text))} chars "
            f"at these settings."
        )
    last = units[fitting - 1].message_number
    if style == "numbers":
        return f"The first {fitting} of the requested messages fit (through #{last})."
    return (
        f"Messages #{first}{EN_DASH}#{last} fit at these settings "
        f"(start={first}, end={last})."
    )


@dataclass
class _RoleStats:
    messages: int = 0
    chars: int = 0
    reasoning: int = 0
    calls: int = 0
    errors: int = 0


def render_overview(view: TraceView) -> str:
    """The ``trace_overview`` output: a summary of the whole trace whose size
    doesn't grow with the trace."""
    messages = view.messages
    total = sum(message.total_chars for message in messages)
    lines = [
        f"Trace: {fmt_count(len(messages), 'message')}, {fmt_number(total)} chars "
        f"({approx_tokens(total)} tokens)",
        *_role_rows(messages),
    ]

    tool_calls_line = _tool_calls_line(messages)
    if tool_calls_line is not None:
        lines.append(tool_calls_line)
    if messages:
        lines.append(_largest_messages_line(messages))

    first_user = next((m for m in messages if m.role == "user" and m.content), None)
    if first_user is not None:
        lines.append(_overview_preview("First user message", first_user))
    last_assistant = next(
        (m for m in reversed(messages) if m.role == "assistant" and m.content), None
    )
    if last_assistant is not None:
        lines.append(
            _overview_preview("Last assistant message with text", last_assistant)
        )
    return "\n".join(lines)


def _role_rows(messages: Sequence[MessageView]) -> list[str]:
    stats: dict[str, _RoleStats] = {}
    for message in messages:
        role_stats = stats.setdefault(message.role, _RoleStats())
        role_stats.messages += 1
        role_stats.chars += len(message.content) + len(message.tool_calls_text)
        role_stats.reasoning += len(message.reasoning)
        role_stats.calls += len(message.tool_calls)
        role_stats.errors += 1 if message.is_error else 0

    other_roles = sorted(role for role in stats if role not in FILTERABLE_ROLES)
    shown_roles = [role for role in FILTERABLE_ROLES if role in stats]
    shown_roles += other_roles[:OVERVIEW_OTHER_ROLES]
    rows = [
        (
            display_name(role),
            fmt_number(stats[role].messages),
            fmt_number(stats[role].chars),
            _role_extras(role, stats[role]),
        )
        for role in shown_roles
    ]
    count_width = max((len(row[1]) for row in rows), default=0)
    chars_width = max((len(row[2]) for row in rows), default=0)
    lines = [
        f"  {role:<9} {count:>{count_width}} {chars:>{chars_width}} chars{extras}"
        for role, count, chars, extras in rows
    ]
    hidden_roles = len(other_roles) - OVERVIEW_OTHER_ROLES
    if hidden_roles > 0:
        lines.append(f"  +{fmt_count(hidden_roles, 'more role')}")
    return lines


def _role_extras(role: str, stats: _RoleStats) -> str:
    extras = ""
    if role == "assistant":
        if stats.reasoning:
            extras += f" (+{fmt_number(stats.reasoning)} reasoning)"
        if stats.calls:
            extras += f", {fmt_count(stats.calls, 'tool call')}"
    if role == "tool" and stats.errors:
        extras += f", {fmt_count(stats.errors, 'error')}"
    return extras


def _tool_calls_line(messages: Sequence[MessageView]) -> str | None:
    counts = Counter(call.name for message in messages for call in message.tool_calls)
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    listed = ", ".join(
        f"{display_name(name)} {TIMES}{fmt_number(count)}"
        for name, count in ranked[:OVERVIEW_TOP_TOOLS]
    )
    remaining = len(ranked) - OVERVIEW_TOP_TOOLS
    if remaining > 0:
        listed += f", +{remaining} more tools"
    return f"Tool calls: {listed}"


def _largest_messages_line(messages: Sequence[MessageView]) -> str:
    largest = heapq.nsmallest(
        OVERVIEW_LARGEST, messages, key=lambda m: (-m.total_chars, m.number)
    )
    listed = f" {MIDDLE_DOT} ".join(
        f"#{m.number} {short_label(m)} {fmt_number(m.total_chars)}" for m in largest
    )
    return f"Largest messages: {listed}"


def _overview_preview(label: str, message: MessageView) -> str:
    return (
        f"{label} (#{message.number}, {fmt_number(len(message.content))} chars): "
        f"{quote(message.content, OVERVIEW_PREVIEW_CHARS)}"
    )


def preview_messages(view: TraceView, args: PreviewArgs) -> str:
    """The ``preview_messages`` output: one line per selected message.

    Raises ``TraceToolUsageError`` for bad arguments or a response over the limit.
    """
    check_filters(args.roles, None)
    start, end = resolve_range(view, args.start, args.end)
    units = [
        Unit(message.number, _preview_line(message, args.preview_chars))
        for message in view.messages[start - 1 : end]
        if role_selected(message, args.roles)
    ]
    if not units:
        return _no_match(start, end, args.roles)
    return assemble(units, None, None, RefusalContext("range", _PREVIEW_ADVICE))


def _no_match(start: int, end: int, roles: Sequence[str] | None) -> str:
    return f"No messages match (#{start}{EN_DASH}#{end}{roles_suffix(roles)})."


def _preview_line(message: MessageView, preview_chars: int) -> str:
    line = f"#{message.number} {display_name(message.role)}"
    if message.tool_name is not None:
        line += f" {display_name(message.tool_name)}"
    line += f" {fmt_number(len(message.content))}"
    if message.is_error:
        line += " ERROR"
    if message.reasoning:
        line += f" (+{fmt_number(len(message.reasoning))} reasoning)"
    if message.tool_calls:
        line += (
            f", calls {_call_names(message.tool_calls)} "
            f"({fmt_number(len(message.tool_calls_text))})"
        )
    if preview_chars > 0 and message.content:
        line += f": {quote(message.content, preview_chars)}"
    return line


def _call_names(calls: Sequence[ToolCallRef]) -> str:
    counts = Counter(call.name for call in calls)
    return ", ".join(
        display_name(name)
        if count == 1
        else f"{display_name(name)} {TIMES}{fmt_number(count)}"
        for name, count in counts.items()
    )


def read_messages(view: TraceView, args: ReadArgs) -> str:
    """The ``read_messages`` output: the text of the selected messages.

    Raises ``TraceToolUsageError`` for bad arguments or a response over the limit.
    """
    check_filters(args.roles, args.parts)
    check_numbers_or_range(args.numbers, args.start, args.end)
    candidates: Sequence[int]
    if args.numbers is not None:
        candidates = sorted(set(args.numbers))
        for number in candidates:
            check_message_number(view, number)
    else:
        start, end = resolve_range(view, args.start, args.end)
        candidates = range(start, end + 1)

    kept: list[MessageView] = []
    excluded: list[str] = []
    for number in candidates:
        message = view.message(number)
        if not role_selected(message, args.roles):
            reason = "role not in roles"
        elif not any(message.part(part) for part in args.parts):
            reason = "no requested parts"
        else:
            kept.append(message)
            continue
        excluded.append(f"#{number} ({reason})")

    footer = (
        f"Not shown: {', '.join(excluded)}"
        if args.numbers is not None and excluded
        else None
    )
    if not kept:
        no_match = _no_match(candidates[0], candidates[-1], args.roles)
        return no_match if footer is None else f"{no_match}\n{footer}"

    units = [
        Unit(message.number, _read_block(view, message, args.parts, args.max_chars))
        for message in kept
    ]
    style: FitStyle = "numbers" if args.numbers is not None else "range"
    return assemble(units, None, footer, RefusalContext(style, _READ_ADVICE))


def _read_block(
    view: TraceView, message: MessageView, parts: Sequence[Part], max_chars: int
) -> str:
    sizes = "; ".join(
        f"{part} {fmt_number(len(message.part(part)))}"
        + ("" if part in parts else " not shown")
        for part in message.non_empty_parts()
    )
    error = " ERROR" if message.is_error else ""
    lines = [f"=== #{message.number} {long_label(message)} ({sizes}){error} ==="]
    for part in BODY_PART_ORDER:
        if part not in parts or not message.part(part):
            continue
        if part == "tool_calls":
            lines.extend(_call_lines(view, message, max_chars))
            continue
        if part == "reasoning":
            lines.append("[reasoning]")
        lines.extend(_cut_part(message, part, max_chars))
    return "\n".join(lines)


def _cut_part(message: MessageView, part: Part, max_chars: int) -> list[str]:
    text = message.part(part)
    if len(text) <= max_chars:
        return [text]
    return [
        text[:max_chars],
        continuation_marker(len(text) - max_chars, message.number, part, max_chars),
    ]


def _call_lines(view: TraceView, message: MessageView, max_chars: int) -> list[str]:
    lines = []
    line_start = 0
    for call in message.tool_calls:
        arguments = call.arguments
        if len(arguments) > max_chars:
            cut_offset = line_start + len(call.name) + 1 + max_chars
            marker = continuation_marker(
                len(arguments) - max_chars, message.number, "tool_calls", cut_offset
            )
            arguments = f"{arguments[:max_chars]} {marker}"
        lines.append(
            f"[call] {call.name} {arguments} {ARROW} {_result_pointer(view, call)}"
        )
        line_start += len(call.name) + 1 + len(call.arguments) + 1
    return lines


def _result_pointer(view: TraceView, call: ToolCallRef) -> str:
    if call.result_number is None:
        return "no result"
    result = view.message(call.result_number)
    status = "ERROR" if result.is_error else "ok"
    return f"#{result.number} {status}, {fmt_number(len(result.content))} chars"


def read_message_text(view: TraceView, args: TextArgs) -> str:
    """The ``read_message_text`` output: a window of one part of one message.

    Raises ``TraceToolUsageError`` for bad arguments.
    """
    check_filters(None, (args.part,))
    check_message_number(view, args.number)
    message = view.message(args.number)
    text = message.part(args.part)
    if not text:
        raise TraceToolUsageError(_missing_part_message(message, args.part))
    if args.offset >= len(text):
        raise TraceToolUsageError(
            f"offset {fmt_number(args.offset)} is past the end of #{message.number} "
            f"{args.part} ({fmt_number(len(text))} chars)."
        )

    end = min(len(text), args.offset + args.max_chars)
    lines = [
        f"=== #{message.number} {long_label(message)} {EM_DASH} {args.part} chars "
        f"{fmt_number(args.offset)}{EN_DASH}{fmt_number(end)} of "
        f"{fmt_number(len(text))} ===",
        text[args.offset : end],
    ]
    if end < len(text):
        lines.append(
            continuation_marker(len(text) - end, message.number, args.part, end)
        )
    return "\n".join(lines)


def _missing_part_message(message: MessageView, part: Part) -> str:
    parts = message.non_empty_parts()
    if not parts:
        return f"Message #{message.number} is empty."
    return f"Message #{message.number} has no {part}. Its parts: {', '.join(parts)}."
