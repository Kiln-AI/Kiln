"""What an episode did to the world, as a net difference rather than a call log.

Seahaven gets this from SQLite's session extension. The stdlib has no session extension, so
the shim computes it: for every tracked table, compare the instance against a read-only
baseline (the fixture file itself when nothing wrote before the agent did, otherwise a
snapshot taken after the startup hooks committed) on the primary key.

Net, not cumulative, is the useful semantics. A rolled-back call leaves nothing. An insert
followed by an update collapses into one insert. A grader reading `final_state.changes` sees
the state the episode reached, not the path it took.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from .db import Db, quote, table_keys


@dataclass(frozen=True)
class Change:
    table: str
    op: Literal["insert", "update", "delete"]
    key: dict[str, Any]
    before: dict[str, Any] | None
    after: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "op": self.op,
            "key": self.key,
            "before": self.before,
            "after": self.after,
        }


def convert(value: Any) -> Any:
    """SQLite storage classes as JSON. Blobs are base64; everything else already is JSON."""
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    return value


def _rank(value: Any) -> tuple[int, Any]:
    """SQLite's own storage-class ordering, so the diff's row order matches `ORDER BY`.

    `World.__init__` refuses a nullable key, so the NULL branch should be unreachable; it is
    kept so the ordering is total whatever a key holds.
    """
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (1, value)
    if isinstance(value, str):
        return (2, value)
    return (3, bytes(value))


def diff(inspection: Db, tables: Sequence[str]) -> list[Change]:
    """Changes to `tables` between the inspection connection's `main` and `base` schemas."""
    conn = inspection.conn
    records: list[Change] = []
    for table in sorted(tables):
        keys, others = table_keys(conn, table)
        if not keys:
            continue
        columns = _columns_in_declaration_order(conn, table)
        on = " AND ".join(f"m.{quote(k)} IS b.{quote(k)}" for k in keys)
        found: list[tuple[tuple[tuple[int, Any], ...], Change]] = []

        for row in _rows(
            conn,
            f"SELECT m.* FROM main.{quote(table)} m "
            f"WHERE NOT EXISTS (SELECT 1 FROM base.{quote(table)} b WHERE {on})",
        ):
            found.append(_record(table, "insert", keys, row, None, row))
        for row in _rows(
            conn,
            f"SELECT b.* FROM base.{quote(table)} b "
            f"WHERE NOT EXISTS (SELECT 1 FROM main.{quote(table)} m WHERE {on})",
        ):
            found.append(_record(table, "delete", keys, row, row, None))
        if others:
            found.extend(_updates(conn, table, keys, others, columns, on))

        found.sort(key=lambda pair: pair[0])
        records.extend(change for _, change in found)
    return records


def _columns_in_declaration_order(conn: Any, table: str) -> list[str]:
    return [
        row[1] for row in conn.execute(f"PRAGMA table_info({quote(table)})").fetchall()
    ]


def _rows(conn: Any, sql: str) -> list[dict[str, Any]]:
    cursor = conn.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _record(
    table: str,
    op: Literal["insert", "update", "delete"],
    keys: Sequence[str],
    key_source: dict[str, Any],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> tuple[tuple[tuple[int, Any], ...], Change]:
    order = tuple(_rank(key_source[k]) for k in keys)
    change = Change(
        table=table,
        op=op,
        key={k: convert(key_source[k]) for k in keys},
        before=None if before is None else {k: convert(v) for k, v in before.items()},
        after=None if after is None else {k: convert(v) for k, v in after.items()},
    )
    return order, change


def _updates(
    conn: Any,
    table: str,
    keys: Sequence[str],
    others: Sequence[str],
    columns: Sequence[str],
    on: str,
) -> list[tuple[tuple[tuple[int, Any], ...], Change]]:
    selected = ", ".join(
        f"b.{quote(c)} AS {quote('b.' + c)}, m.{quote(c)} AS {quote('m.' + c)}"
        for c in columns
    )
    unchanged = " AND ".join(f"m.{quote(c)} IS b.{quote(c)}" for c in others)
    rows = _rows(
        conn,
        f"SELECT {selected} FROM main.{quote(table)} m "
        f"JOIN base.{quote(table)} b ON {on} WHERE NOT ({unchanged})",
    )
    records = []
    for row in rows:
        changed = [c for c in others if not _same(row[f"b.{c}"], row[f"m.{c}"])]
        before = {k: row[f"b.{k}"] for k in keys}
        after = {k: row[f"m.{k}"] for k in keys}
        before.update({c: row[f"b.{c}"] for c in changed})
        after.update({c: row[f"m.{c}"] for c in changed})
        records.append(_record(table, "update", keys, after, before, after))
    return records


def _same(before: Any, after: Any) -> bool:
    if before is None or after is None:
        return before is None and after is None
    return convert(before) == convert(after)


def digest(inspection: Db, tables: Sequence[str], schema_hash: str) -> str:
    """A SHA-256 over every tracked row. Equal digests mean equal tracked state; the schema
    hash is folded in so two worlds with different shapes never collide."""
    conn = inspection.conn
    running = hashlib.sha256(schema_hash.encode("utf-8"))
    for table in sorted(tables):
        keys, _ = table_keys(conn, table)
        if not keys:
            continue
        running.update(f"{table}\n".encode("utf-8"))
        order = ", ".join(quote(k) for k in keys)
        for row in conn.execute(
            f"SELECT * FROM main.{quote(table)} ORDER BY {order}"
        ).fetchall():
            rendered = json.dumps(
                [convert(value) for value in row],
                separators=(",", ":"),
                ensure_ascii=False,
            )
            running.update(rendered.encode("utf-8") + b"\n")
    return running.hexdigest()
