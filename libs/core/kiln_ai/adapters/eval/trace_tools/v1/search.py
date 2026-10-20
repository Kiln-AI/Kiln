import json
import time
from dataclasses import dataclass
from typing import Any

import regex

from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.limits import (
    SEARCH_CONTEXT_DEFAULT,
    SEARCH_COUNT_DEFAULT,
    SEARCH_TIMEOUT_SECONDS,
)
from kiln_ai.adapters.eval.trace_tools.v1.pattern_check import check_regex_pattern
from kiln_ai.adapters.eval.trace_tools.v1.render import (
    BODY_PART_ORDER,
    DEFAULT_PARTS,
    EN_DASH,
    RefusalContext,
    Unit,
    assemble,
    check_filters,
    fmt_count,
    resolve_range,
    role_selected,
    short_label,
)
from kiln_ai.adapters.eval.trace_tools.v1.view import MessageView, Part, TraceView

__all__ = ["SearchArgs", "search_trace"]

_SEARCH_ADVICE = (
    "use a lower count or context_chars, a roles, parts or start/end filter, "
    "or a more specific pattern"
)

# The regex package exports its flags through star imports that ty can't follow.
# VERSION0 pins re-compatible syntax even if a host changes regex.DEFAULT_VERSION.
_VERSION0: int = regex.VERSION0  # type: ignore[unresolved-attribute]
_IGNORECASE: int = regex.IGNORECASE  # type: ignore[unresolved-attribute]


@dataclass(frozen=True)
class SearchArgs:
    """Arguments of ``search_trace``, with defaults applied."""

    pattern: str
    regex: bool = False
    case_sensitive: bool = False
    roles: tuple[str, ...] | None = None
    parts: tuple[Part, ...] = DEFAULT_PARTS
    context_chars: int = SEARCH_CONTEXT_DEFAULT
    start: int | None = None
    end: int | None = None
    count: int = SEARCH_COUNT_DEFAULT
    offset: int = 0


@dataclass(frozen=True)
class _Match:
    message: MessageView
    part: Part
    start: int
    end: int


def search_trace(
    view: TraceView,
    args: SearchArgs,
    *,
    timeout_seconds: float = SEARCH_TIMEOUT_SECONDS,
) -> str:
    """The ``search_trace`` output: the address of each match on the requested page.

    Every match is counted, but only the requested page is kept, so a pattern
    that matches millions of times costs time, not memory. Raises
    ``TraceToolUsageError`` for bad arguments, a regex that is invalid or too
    large to compile, a search that runs past ``timeout_seconds``, or a response
    over the limit.
    """
    check_filters(args.roles, args.parts)
    if not args.pattern:
        raise TraceToolUsageError("pattern must not be empty.")
    start, end = resolve_range(view, args.start, args.end)
    pattern = _compile(args)

    deadline = time.monotonic() + timeout_seconds
    page_end = args.offset + args.count
    page: list[_Match] = []
    total = 0
    messages_with_matches = 0
    for message in view.messages[start - 1 : end]:
        if not role_selected(message, args.roles):
            continue
        message_total = total
        for part in BODY_PART_ORDER:
            text = message.part(part)
            if part not in args.parts or not text:
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _timed_out(timeout_seconds)
            try:
                # concurrent=True releases the GIL so a slow regex can't stall the event
                # loop, at the cost of a handoff per match and part that slows parallel
                # searches sharply. Literal scans of real text are quick, so keep it.
                matches = pattern.finditer(
                    text, timeout=remaining, concurrent=args.regex
                )
                for match in matches:
                    match_start, match_end = match.span()
                    if match_end <= match_start:
                        continue
                    if args.offset <= total < page_end:
                        page.append(_Match(message, part, match_start, match_end))
                    total += 1
            except TimeoutError:
                raise _timed_out(timeout_seconds) from None
        if total > message_total:
            messages_with_matches += 1

    if total == 0:
        return f"No matches for {json.dumps(args.pattern, ensure_ascii=False)}."
    if args.offset >= total:
        raise TraceToolUsageError(
            f"offset {args.offset} is past the last match "
            f"({fmt_count(total, 'match', 'matches')})."
        )

    shown_through = args.offset + len(page)
    header = (
        f"{fmt_count(total, 'match', 'matches')} in "
        f"{fmt_count(messages_with_matches, 'message')}. "
        f"Showing matches {args.offset + 1}{EN_DASH}{shown_through}."
    )
    more_footer = f"Use offset={shown_through} for more."
    units = [
        Unit(match.message.number, _match_line(match, args.context_chars))
        for match in page
    ]
    return assemble(
        units,
        header,
        more_footer if shown_through < total else None,
        RefusalContext("matches", _SEARCH_ADVICE, fit_footer=more_footer),
    )


def _compile(args: SearchArgs) -> Any:
    flags = _VERSION0 if args.case_sensitive else _VERSION0 | _IGNORECASE
    # Without cache_pattern=False, the regex package keeps up to 500 compiled
    # patterns for the life of the process, several MB each for large ones.
    if not args.regex:
        return regex.compile(regex.escape(args.pattern), flags, cache_pattern=False)
    check_regex_pattern(args.pattern)
    try:
        return regex.compile(args.pattern, flags, cache_pattern=False)
    except regex.error as e:
        raise _invalid_regex(str(e)) from None
    except RecursionError:
        raise _invalid_regex("groups are nested too deeply") from None


def _invalid_regex(reason: str) -> TraceToolUsageError:
    return TraceToolUsageError(
        f"Invalid regex: {reason}. Use regex=false to search plain text."
    )


def _timed_out(timeout_seconds: float) -> TraceToolUsageError:
    return TraceToolUsageError(
        f"Search timed out after {timeout_seconds:g} seconds. Use a simpler "
        "pattern, or narrow it with start/end, roles or parts."
    )


def _match_line(match: _Match, context_chars: int) -> str:
    line = (
        f"#{match.message.number} {short_label(match.message)} {match.part} "
        f"@{match.start}"
    )
    if context_chars <= 0:
        return line
    text = match.message.part(match.part)
    snippet_start = max(0, match.start - context_chars)
    snippet_end = min(len(text), match.end + context_chars)
    before = "<truncated> " if snippet_start > 0 else ""
    after = " <truncated>" if snippet_end < len(text) else ""
    snippet = json.dumps(text[snippet_start:snippet_end], ensure_ascii=False)
    return f"{line}: {before}{snippet}{after}"
