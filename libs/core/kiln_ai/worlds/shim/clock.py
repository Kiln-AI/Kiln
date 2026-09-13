"""The instance clock, and the SQLite functions that make the database agree with it.

A world is deterministic only if "now" is. `Clock` holds one instant, frozen at the
fixture's timestamp, and `register_clock_functions` overrides SQLite's date and time
functions on the instance connection so a `DEFAULT (datetime('now'))`, a trigger or a
`WHERE due < date('now')` all read the same instant the Python side reads.

Unlike Seahaven's clock this one moves: `advance` and `set` exist because the fixture
loader replays a company's history and the harness needs to sit at a chosen date. The
overrides read `clock.now()` at call time, so a move takes effect on the next statement
with no re-registration.

The `'localtime'` and `'utc'` modifiers are refused rather than passed through: both read
the host machine's timezone, so a world using one would answer differently on every machine,
which is the whole thing this module exists to prevent. SQLite collapses the refusal into
"user-defined function raised exception", so what a world author sees is an opaque
`DbError` — but they see it on the first run, rather than a divergence months later.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .errors import WorldBug

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_CANONICAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class Clock:
    """One UTC instant, rendered in the canonical `2026-03-04T05:06:07.008Z` form."""

    def __init__(self, now: datetime) -> None:
        if not isinstance(now, datetime):
            raise WorldBug(f"clock needs a datetime, got {type(now).__name__}")
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise WorldBug(
                "clock needs a timezone-aware datetime; a naive one would mean the "
                "world's 'now' depends on the machine's timezone"
            )
        self._now = now.astimezone(timezone.utc)

    __hash__ = None  # type: ignore[assignment]  # mutable: advance() and set() move it

    def now(self) -> datetime:
        return self._now

    def iso(self) -> str:
        return self._now.strftime(ISO_FORMAT)[:-4] + "Z"

    @classmethod
    def from_iso(cls, text: str) -> "Clock":
        if not isinstance(text, str) or not _CANONICAL.match(text):
            raise WorldBug(
                f"not a canonical world timestamp: {text!r} "
                "(expected YYYY-MM-DDTHH:MM:SS.mmmZ)"
            )
        return cls(datetime.strptime(text, ISO_FORMAT).replace(tzinfo=timezone.utc))

    @classmethod
    def wall(cls) -> "Clock":
        now = datetime.now(timezone.utc)
        return cls(now.replace(microsecond=(now.microsecond // 1000) * 1000))

    def advance(self, delta: timedelta) -> datetime:
        if not isinstance(delta, timedelta):
            raise WorldBug(f"advance needs a timedelta, got {type(delta).__name__}")
        if delta < timedelta(0):
            raise WorldBug("a world clock never runs backwards; use set() instead")
        self._now = self._now + delta
        return self._now

    def set(self, now: "datetime | str") -> datetime:
        self._now = (
            Clock.from_iso(now)._now if isinstance(now, str) else Clock(now)._now
        )
        return self._now

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Clock):
            return NotImplemented
        return self._now == other._now

    def __repr__(self) -> str:
        return f"Clock({self.iso()})"


# Each entry is (name, index of the first argument that may be a time value, the argument
# count at which `'now'` is appended). `strftime` starts at 1 so a format string that
# happens to read "now" is left alone; `timediff` never gets an implicit `'now'`.
_TIME_FUNCTIONS: tuple[tuple[str, int, int | None], ...] = (
    ("date", 0, 0),
    ("time", 0, 0),
    ("datetime", 0, 0),
    ("julianday", 0, 0),
    ("unixepoch", 0, 0),
    ("strftime", 1, 1),
    ("timediff", 0, None),
)

# Timezone modifiers: host-dependent, and meaningless in a world frozen to one UTC instant.
_REFUSED_MODIFIERS = frozenset({"localtime", "utc"})

# SQLite's parser rewrites these keywords into calls of the same name, so overriding the
# function covers the constant.
_CURRENT_FUNCTIONS: tuple[tuple[str, str], ...] = (
    ("current_timestamp", "datetime"),
    ("current_date", "date"),
    ("current_time", "time"),
)


def register_clock_functions(
    conn: sqlite3.Connection, clock: Clock
) -> sqlite3.Connection:
    """Override SQLite's time functions on `conn` so they read `clock`.

    Returns the private helper connection the overrides evaluate against; the owning `Db`
    closes it. Application-defined functions win over built-ins in SQLite's lookup, so the
    helper is where the real implementations still live.
    """
    helper = sqlite3.connect(":memory:", check_same_thread=False)

    def evaluate(name: str, values: list[Any]) -> Any:
        placeholders = ",".join("?" * len(values))
        return helper.execute(f"SELECT {name}({placeholders})", values).fetchone()[0]

    def make_time_function(name: str, first_time_index: int, implicit_at: int | None):
        def run(*args: Any) -> Any:
            values = list(args)
            if implicit_at is not None and len(values) == implicit_at:
                values.append("now")
            substituted = []
            for index, value in enumerate(values):
                folded = value.lower() if isinstance(value, str) else None
                if folded is not None and index >= first_time_index:
                    if folded in _REFUSED_MODIFIERS:
                        # SQLite flattens any exception raised by an application-defined
                        # function into "user-defined function raised exception", so this
                        # text is for whoever reads the source; the statement failing at all
                        # is the point. SQLite matches these modifiers case-insensitively
                        # and rejects padded forms outright, so this matches the same set.
                        raise WorldBug(
                            f"the '{folded}' modifier reads the host machine's timezone, so "
                            "this SQL would answer differently on every machine; the "
                            "world's clock is UTC"
                        )
                    if folded == "now":
                        substituted.append(clock.iso())
                        continue
                substituted.append(value)
            return evaluate(name, substituted)

        return run

    def make_current_function(underlying: str):
        def run(*args: Any) -> Any:
            return evaluate(underlying, [clock.iso()])

        return run

    for name, first_time_index, implicit_at in _TIME_FUNCTIONS:
        conn.create_function(
            name,
            -1,
            make_time_function(name, first_time_index, implicit_at),
            deterministic=True,
        )
    for name, underlying in _CURRENT_FUNCTIONS:
        conn.create_function(
            name, -1, make_current_function(underlying), deterministic=True
        )
    return helper
