from __future__ import annotations

import sqlite3
import sys

import pytest

from .clock import Clock
from .db import build_blank, open_inspection, open_instance, table_keys, world_tables
from .errors import DbError, WorldBug

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)

DDL = """
CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL, note TEXT) STRICT;
CREATE TABLE tags (item_id TEXT NOT NULL, tag TEXT NOT NULL, weight INTEGER NOT NULL,
                   PRIMARY KEY (tag, item_id)) STRICT;
"""


@pytest.fixture
def clock() -> Clock:
    return Clock.from_iso("2026-03-04T05:06:07.008Z")


@pytest.fixture
def db(tmp_path, clock):
    path = tmp_path / "state.sqlite"
    build_blank(path, DDL).close()
    connection = open_instance(path, clock)
    connection.execute("INSERT INTO items (id, name) VALUES ('i1', 'first')")
    try:
        yield connection
    finally:
        connection.close()


def test_rows_are_dicts_last_duplicate_wins(db):
    assert db.rows("SELECT id, name FROM items") == [{"id": "i1", "name": "first"}]
    assert db.one("SELECT 1 AS x, 2 AS x") == {"x": 2}
    assert db.one("SELECT id FROM items WHERE id = 'nope'") is None


def test_db_error_wraps_with_code(db):
    with pytest.raises(DbError) as caught:
        db.rows("SELECT * FROM missing_table")
    assert caught.value.code == "db_error"
    assert caught.value.message == "database error"
    assert "missing_table" in caught.value.sqlite_message
    assert caught.value.sqlite_code == sqlite3.SQLITE_ERROR


def test_transaction_nesting_savepoint_rollback_keeps_outer(db):
    with db.transaction():
        db.execute("INSERT INTO items (id, name) VALUES ('outer', 'o')")
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.execute("INSERT INTO items (id, name) VALUES ('inner', 'i')")
                raise RuntimeError("nope")
        assert db.in_transaction
    assert [r["id"] for r in db.rows("SELECT id FROM items ORDER BY id")] == [
        "i1",
        "outer",
    ]


def test_transaction_exception_rolls_back_top_level(db):
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.execute("INSERT INTO items (id, name) VALUES ('x', 'x')")
            raise RuntimeError("nope")
    assert db.one("SELECT id FROM items WHERE id = 'x'") is None
    assert not db.in_transaction


def test_in_transaction_reflects_depth(db):
    assert not db.in_transaction
    with db.transaction():
        assert db.in_transaction
        with db.transaction():
            assert db.in_transaction
        assert db.in_transaction
    assert not db.in_transaction


def test_executemany_and_exec_fields(db):
    assert (
        db.executemany(
            "INSERT INTO tags (item_id, tag, weight) VALUES (?, ?, ?)",
            [("i1", "red", 1), ("i1", "blue", 2)],
        )
        == 2
    )
    result = db.execute("UPDATE tags SET weight = 9 WHERE item_id = 'i1'")
    assert result.rowcount == 2
    assert isinstance(result.last_rowid, int)


def test_inspection_refuses_insert_and_journal_pragma_allows_select_and_table_info(
    tmp_path, clock, db
):
    inspection = open_inspection(tmp_path / "state.sqlite", clock)
    try:
        assert inspection.rows("SELECT id FROM items") == [{"id": "i1"}]
        assert [row["name"] for row in inspection.rows("PRAGMA table_info(items)")] == [
            "id",
            "name",
            "note",
        ]
        with pytest.raises(DbError):
            inspection.execute("INSERT INTO items (id, name) VALUES ('x', 'x')")
        with pytest.raises(DbError):
            inspection.rows("PRAGMA journal_mode")
        with pytest.raises(DbError):
            inspection.execute("DROP TABLE items")
        with pytest.raises(DbError):
            inspection.execute("CREATE TABLE sneaky (id TEXT PRIMARY KEY)")
    finally:
        inspection.close()


def test_inspection_attach_then_authorizer_denies_further_attach(tmp_path, clock, db):
    other = tmp_path / "other.sqlite"
    build_blank(other, DDL).close()
    inspection = open_inspection(
        tmp_path / "state.sqlite", clock, attach={"base": other}
    )
    try:
        assert inspection.rows("SELECT id FROM base.items") == []
        with pytest.raises(DbError):
            inspection.execute(f"ATTACH '{other}' AS extra")
    finally:
        inspection.close()


def test_busy_timeout_zero_second_writer_fails_immediately(tmp_path, clock, db):
    second = open_instance(tmp_path / "state.sqlite", clock)
    try:
        with db.transaction():
            db.execute("INSERT INTO items (id, name) VALUES ('held', 'h')")
            with pytest.raises(DbError) as caught:
                with second.transaction():
                    second.execute("INSERT INTO items (id, name) VALUES ('other', 'o')")
        assert "locked" in caught.value.sqlite_message.lower()
    finally:
        second.close()


def test_defensive_config_set(db):
    assert db.conn.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE) is True


def test_build_blank_refuses_existing_file(tmp_path):
    path = tmp_path / "state.sqlite"
    build_blank(path, DDL).close()
    with pytest.raises(WorldBug, match="which exists"):
        build_blank(path, DDL)


def test_build_blank_reports_bad_ddl():
    with pytest.raises(WorldBug, match="schema failed to run"):
        build_blank(":memory:", "CREATE TABLE (;")


def test_table_keys_pk_order_and_columns(db):
    assert table_keys(db.conn, "items") == (["id"], ["name", "note"])
    assert table_keys(db.conn, "tags") == (["tag", "item_id"], ["weight"])
    assert world_tables(db.conn) == ["items", "tags"]


def test_dict_param_is_world_bug(db):
    with pytest.raises(WorldBug, match="positional"):
        db.rows("SELECT * FROM items WHERE id = :id", {"id": "i1"})
    with pytest.raises(WorldBug, match="positional"):
        db.executemany("INSERT INTO items (id, name) VALUES (?, ?)", [({"a": 1}, "x")])


def test_close_is_idempotent(tmp_path, clock):
    path = tmp_path / "closeme.sqlite"
    build_blank(path, DDL).close()
    connection = open_instance(path, clock)
    connection.close()
    connection.close()
