"""Does this database still have the shape the world declares?

Run before a fixture is frozen. A fixture whose schema has drifted from the world's DDL —
an index added by hand, a column reordered by a rebuild, a leftover scratch table — would
load fine and then diverge in ways that look like world bugs, so freezing refuses it.
"""

from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING

from .db import build_blank
from .errors import WorldBug

if TYPE_CHECKING:
    from .world import World

_OBJECT_TYPES = ("table", "index", "trigger", "view")


def schema_map(conn: sqlite3.Connection) -> dict[str, str]:
    """`"<type> <name>"` → the object's whitespace-collapsed DDL.

    Objects SQLite creates for itself (`sqlite_%`, and the implicit indexes behind
    `UNIQUE`/`PRIMARY KEY`, which carry no SQL) are left out: they follow from the
    declarations that are compared.
    """
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
    ).fetchall()
    return {
        f"{kind} {name}": re.sub(r"\s+", " ", sql).strip()
        for kind, name, sql in rows
        if kind in _OBJECT_TYPES
    }


def differences(actual: dict[str, str], expected: dict[str, str]) -> list[str]:
    lines = []
    for key in sorted(set(actual) | set(expected)):
        if key not in expected:
            lines.append(f"unexpected {key}")
        elif key not in actual:
            lines.append(f"missing {key}")
        elif actual[key] != expected[key]:
            lines.append(
                f"{key} differs: schema declares {expected[key]!r}, "
                f"database has {actual[key]!r}"
            )
    return lines


def check(conn: sqlite3.Connection, world: "World") -> None:
    reference = build_blank(":memory:", world.schema)
    try:
        expected = schema_map(reference)
    finally:
        reference.close()
    found = differences(schema_map(conn), expected)
    if found:
        raise WorldBug(
            "this database no longer matches the world's schema: " + "; ".join(found)
        )
