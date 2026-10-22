"""Rejects search patterns that would be too expensive to compile.

The regex package expands counted repeats when it compiles a pattern, so
``a{100000000}`` builds a hundred million nodes. Compiling has no time limit
and holds the GIL, so this check runs before ``regex.compile``. It is a best
effort against accidental blow-ups, not a guarantee: a deliberately crafted
pattern can still be slow to compile.
"""

import re
from dataclasses import dataclass

from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.limits import SEARCH_PATTERN_ELEMENTS_MAX

__all__ = ["check_regex_pattern", "pattern_elements"]

_COUNTED_REPEAT = re.compile(r"\{(\d*)(?:,(\d*))?\}")
_INLINE_FLAGS = re.compile(r"\(\?([a-zA-Z0-9-]*)[:)]")
# Verbose mode (x) lets whitespace and comments sit between an item and its
# counted repeat, which pattern_elements doesn't model. Full case folding (f)
# makes large character classes far slower to compile.
_UNSUPPORTED_FLAGS = frozenset("xf")
_BRACED_ESCAPES = frozenset("pPN")
_UNCOUNTED_QUANTIFIERS = frozenset("*+?")
# Bounds of 10 or more digits are over any limit; int() of a huge digit string
# raises in Python 3.11+.
_MAX_BOUND_DIGITS = 9


def check_regex_pattern(pattern: str) -> None:
    """Raise ``TraceToolUsageError`` for a regex search pattern that looks too
    expensive to compile, or that turns on an unsupported inline flag."""
    if any(
        _UNSUPPORTED_FLAGS & set(flags.group(1).partition("-")[0])
        for flags in _INLINE_FLAGS.finditer(pattern)
    ):
        raise TraceToolUsageError(
            "Verbose mode (?x) and full case folding (?f) aren't supported in "
            "search patterns. Write the pattern without them."
        )
    if pattern_elements(pattern) > SEARCH_PATTERN_ELEMENTS_MAX:
        raise TraceToolUsageError(
            "Pattern too large: it would compile to over "
            f"{SEARCH_PATTERN_ELEMENTS_MAX:,} elements. Use smaller {{m,n}} "
            "repeat counts (or * and + instead), or a shorter pattern."
        )


@dataclass
class _Group:
    alternatives: int = 0
    """The size of the alternatives before the current one, each at least 1."""
    current: int = 0
    """The size of the current alternative so far."""

    def size(self) -> int:
        return self.alternatives + max(1, self.current)


def pattern_elements(pattern: str) -> int:
    """An estimate of the number of elements the regex package builds when it
    compiles ``pattern`` without verbose mode.

    Every character, escape and character class counts as one element. A group
    counts as 1 plus its alternatives, each at least 1, so empty groups count
    too. A counted repeat multiplies the item before it by its largest bound.
    Counting may stop early once a counted repeat passes the limit; the result
    is then over the limit but not the full estimate.
    """
    groups = [_Group()]
    last_item = 0
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "(":
            groups.append(_Group())
            last_item = 0
            index += 1
            continue
        if char == ")" and len(groups) > 1:
            last_item = 1 + groups.pop().size()
            groups[-1].current += last_item
            index += 1
            continue
        if char == "|":
            groups[-1].alternatives += max(1, groups[-1].current)
            groups[-1].current = 0
            last_item = 0
            index += 1
            continue
        if char in _UNCOUNTED_QUANTIFIERS:
            index += 1
            continue
        repeat = _COUNTED_REPEAT.match(pattern, index) if char == "{" else None
        if repeat is not None and (repeat.group(1) or repeat.group(2)):
            factor = max(1, _bound(repeat.group(1)), _bound(repeat.group(2)))
            groups[-1].current += last_item * (factor - 1)
            last_item *= factor
            if groups[-1].current > SEARCH_PATTERN_ELEMENTS_MAX:
                return groups[-1].current
            index = repeat.end()
            continue
        index = _item_end(pattern, index)
        groups[-1].current += 1
        last_item = 1
    return sum(group.size() for group in groups)


def _bound(digits: str | None) -> int:
    significant = (digits or "").lstrip("0")
    if len(significant) > _MAX_BOUND_DIGITS:
        return SEARCH_PATTERN_ELEMENTS_MAX + 1
    return int(significant or "0")


def _item_end(pattern: str, index: int) -> int:
    """Where the single character, escape or character class at ``index`` ends."""
    char = pattern[index]
    if char == "\\":
        end = index + 2
        is_braced = pattern[index + 1 : end] in _BRACED_ESCAPES
        if is_braced and pattern.startswith("{", end):
            closing = pattern.find("}", end)
            return len(pattern) if closing == -1 else closing + 1
        return end
    if char == "[":
        return _class_end(pattern, index)
    return index + 1


def _class_end(pattern: str, index: int) -> int:
    end = index + 1
    if pattern.startswith("^", end):
        end += 1
    # A "]" right after the opening "[" (or "[^") is a literal, not the end.
    if pattern.startswith("]", end):
        end += 1
    while end < len(pattern) and pattern[end] != "]":
        end += 2 if pattern[end] == "\\" else 1
    return end + 1
