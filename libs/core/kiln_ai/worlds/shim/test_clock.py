from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

from .clock import Clock, register_clock_functions
from .errors import WorldBug

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)

NOW = "2026-03-04T05:06:07.008Z"


@pytest.fixture
def clock() -> Clock:
    return Clock.from_iso(NOW)


@pytest.fixture
def conn(clock):
    connection = sqlite3.connect(":memory:")
    helper = register_clock_functions(connection, clock)
    try:
        yield connection
    finally:
        connection.close()
        helper.close()


def test_naive_datetime_refused():
    with pytest.raises(WorldBug, match="timezone-aware"):
        Clock(datetime(2026, 3, 4, 5, 6, 7))


def test_iso_canonical_and_ms_truncated():
    clock = Clock(datetime(2026, 3, 4, 5, 6, 7, 8999, tzinfo=timezone.utc))
    assert clock.iso() == "2026-03-04T05:06:07.008Z"


def test_iso_converts_to_utc():
    offset = timezone(timedelta(hours=2))
    clock = Clock(datetime(2026, 3, 4, 7, 6, 7, tzinfo=offset))
    assert clock.iso() == "2026-03-04T05:06:07.000Z"


@pytest.mark.parametrize(
    "text",
    [
        "2026-03-04T05:06:07Z",
        "2026-03-04T05:06:07.00Z",
        "2026-03-04T05:06:07.008",
        "2026-03-04 05:06:07.008Z",
        "2026-03-04T05:06:07.008+00:00",
        "not a time",
    ],
)
def test_from_iso_rejects_non_canonical(text):
    with pytest.raises(WorldBug, match="canonical"):
        Clock.from_iso(text)


def test_wall_truncates_to_ms():
    assert Clock.wall().now().microsecond % 1000 == 0


def test_advance_moves_now_and_refuses_negative(clock):
    assert (
        clock.advance(timedelta(days=1, milliseconds=2))
        .isoformat()
        .startswith("2026-03-05T05:06:07.010")
    )
    assert clock.iso() == "2026-03-05T05:06:07.010Z"
    with pytest.raises(WorldBug, match="backwards"):
        clock.advance(timedelta(seconds=-1))


def test_set_accepts_datetime_and_iso(clock):
    clock.set("2020-01-01T00:00:00.000Z")
    assert clock.iso() == "2020-01-01T00:00:00.000Z"
    clock.set(datetime(2021, 2, 3, tzinfo=timezone.utc))
    assert clock.iso() == "2021-02-03T00:00:00.000Z"
    with pytest.raises(WorldBug, match="timezone-aware"):
        clock.set(datetime(2021, 2, 3))


def test_clock_not_hashable(clock):
    assert clock == Clock.from_iso(NOW)
    assert clock != Clock.from_iso("2020-01-01T00:00:00.000Z")
    assert clock != "2026-03-04T05:06:07.008Z"
    with pytest.raises(TypeError):
        hash(clock)


@pytest.mark.parametrize(
    "expression, reference",
    [
        ("date('now')", "date(?)"),
        ("date()", "date(?)"),
        ("date('now', '+1 day')", "date(?, '+1 day')"),
        ("date('now', 'start of month')", "date(?, 'start of month')"),
        ("time('now')", "time(?)"),
        ("time()", "time(?)"),
        ("datetime('now')", "datetime(?)"),
        ("datetime()", "datetime(?)"),
        ("datetime('now', '-2 hours')", "datetime(?, '-2 hours')"),
        ("julianday('now')", "julianday(?)"),
        ("julianday()", "julianday(?)"),
        ("unixepoch('now')", "unixepoch(?)"),
        ("unixepoch()", "unixepoch(?)"),
        ("strftime('%Y-%m-%d', 'now')", "strftime('%Y-%m-%d', ?)"),
        ("strftime('%s', 'now', '+1 month')", "strftime('%s', ?, '+1 month')"),
        ("strftime('%Y')", "strftime('%Y', ?)"),
        ("timediff('now', '2020-01-01')", "timediff(?, '2020-01-01')"),
    ],
)
def test_sql_overrides_match_sqlite_on_helper(conn, expression, reference):
    """The override must equal what SQLite itself answers with the clock's instant
    substituted for the time value; anything else is a silent divergence in a world's SQL."""
    plain = sqlite3.connect(":memory:")
    try:
        expected = plain.execute(f"SELECT {reference}", (NOW,)).fetchone()[0]
    finally:
        plain.close()
    assert conn.execute(f"SELECT {expression}").fetchone()[0] == expected


def test_current_timestamp_keywords_yield_clock(conn):
    row = conn.execute(
        "SELECT current_timestamp, current_date, current_time"
    ).fetchone()
    assert row == ("2026-03-04 05:06:07", "2026-03-04", "05:06:07")


def test_trigger_and_default_yield_clock(conn):
    conn.execute(
        "CREATE TABLE t (id INTEGER PRIMARY KEY, made TEXT DEFAULT (datetime('now')), "
        "touched TEXT)"
    )
    conn.execute(
        "CREATE TRIGGER stamp AFTER INSERT ON t BEGIN "
        "UPDATE t SET touched = datetime('now') WHERE id = NEW.id; END"
    )
    conn.execute("INSERT INTO t (id) VALUES (1)")
    assert conn.execute("SELECT made, touched FROM t").fetchone() == (
        "2026-03-04 05:06:07",
        "2026-03-04 05:06:07",
    )


def test_strftime_now_as_format_not_substituted(conn):
    """'now' in strftime's first argument is a format string, not a time value."""
    assert conn.execute("SELECT strftime('now')").fetchone()[0] == "now"
    assert conn.execute("SELECT strftime('now', 'now')").fetchone()[0] == "now"


def test_advance_visible_in_next_statement(conn, clock):
    assert conn.execute("SELECT date('now')").fetchone()[0] == "2026-03-04"
    clock.advance(timedelta(days=2))
    assert conn.execute("SELECT date('now')").fetchone()[0] == "2026-03-06"
    clock.set("2019-12-31T00:00:00.000Z")
    assert conn.execute("SELECT date('now')").fetchone()[0] == "2019-12-31"


@pytest.mark.parametrize(
    "expression",
    [
        "datetime('now', 'localtime')",
        "datetime('2020-01-01', 'LOCALTIME')",
        "date('now', 'utc')",
        "strftime('%Y', 'now', 'localtime')",
    ],
)
def test_timezone_modifiers_refused(conn, expression):
    """'localtime' and 'utc' read the host machine's timezone. A world that used one would
    answer differently on every machine, so the statement fails instead."""
    with pytest.raises(sqlite3.OperationalError):
        conn.execute(f"SELECT {expression}").fetchone()


def test_timezone_words_outside_a_time_position_are_untouched(conn):
    assert conn.execute("SELECT strftime('localtime')").fetchone()[0] == "localtime"


def test_now_matching_is_case_insensitive_and_exact(conn):
    assert conn.execute("SELECT date('NOW')").fetchone()[0] == "2026-03-04"
    assert conn.execute("SELECT date(' now ')").fetchone()[0] is None
