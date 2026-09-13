from __future__ import annotations

import sqlite3
import sys

import pytest

from .conformance import check, differences, schema_map
from .db import build_blank
from .errors import WorldBug

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)

SCHEMA = """
CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL) STRICT;
CREATE INDEX items_by_name ON items (name);
"""


@pytest.fixture
def live() -> sqlite3.Connection:
    conn = build_blank(":memory:", SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


class FakeWorld:
    schema = SCHEMA


def test_identical_passes(live):
    check(live, FakeWorld())
    assert set(schema_map(live)) == {"table items", "index items_by_name"}
    assert differences(schema_map(live), schema_map(live)) == []


def test_column_order_flagged(live):
    reordered = build_blank(
        ":memory:",
        "CREATE TABLE items (name TEXT NOT NULL, id TEXT PRIMARY KEY) STRICT;\n"
        "CREATE INDEX items_by_name ON items (name);",
    )
    try:
        found = differences(schema_map(reordered), schema_map(live))
        assert len(found) == 1 and found[0].startswith("table items differs")
        with pytest.raises(WorldBug, match="no longer matches"):
            check(reordered, FakeWorld())
    finally:
        reordered.close()


def test_extra_index_flagged(live):
    live.execute("CREATE INDEX items_extra ON items (id, name)")
    with pytest.raises(WorldBug, match="unexpected index items_extra"):
        check(live, FakeWorld())


def test_extra_table_flagged(live):
    live.execute("CREATE TABLE scratch (id TEXT PRIMARY KEY) STRICT")
    with pytest.raises(WorldBug, match="unexpected table scratch"):
        check(live, FakeWorld())


def test_missing_table_flagged(live):
    live.execute("DROP INDEX items_by_name")
    with pytest.raises(WorldBug, match="missing index items_by_name"):
        check(live, FakeWorld())


def test_whitespace_is_not_a_difference():
    spaced = build_blank(
        ":memory:",
        "CREATE TABLE items (id   TEXT PRIMARY KEY,\n  name TEXT NOT NULL) STRICT;\n"
        "CREATE INDEX items_by_name ON items (name);",
    )
    tight = build_blank(":memory:", SCHEMA)
    try:
        assert differences(schema_map(spaced), schema_map(tight)) == []
    finally:
        spaced.close()
        tight.close()
