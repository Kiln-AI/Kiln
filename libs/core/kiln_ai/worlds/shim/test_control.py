from __future__ import annotations

import sys

import pytest

from .control import controller_digest
from .ctx import Ctx
from .errors import ArgumentError, ToolError, WorldBug

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


@pytest.fixture
def loaded(toy_world, frozen):
    instance = toy_world.instance("base")
    try:
        yield instance
    finally:
        instance.destroy()


def test_run_sql_sees_all_tables_and_pragma_table_info(loaded):
    result = loaded.call(
        "controller_run_sql", sql="SELECT id, name FROM items ORDER BY id"
    )
    assert result == {
        "columns": ["id", "name"],
        "rows": [["i1", "first"], ["i2", "second"]],
        "row_count": 2,
        "truncated": False,
    }
    assert loaded.call(
        "controller_run_sql",
        sql="SELECT n FROM counters WHERE name = ?",
        params=["adds"],
    )["rows"] == [[0]]
    columns = loaded.call("controller_run_sql", sql="PRAGMA table_info(items)")
    assert [row[1] for row in columns["rows"]] == [
        "id",
        "name",
        "done",
        "note",
        "payload",
    ]
    assert (
        loaded.call("controller_run_sql", sql="SELECT id FROM base.items")["row_count"]
        == 2
    )


def test_run_sql_write_refused_with_sqlite_text(loaded):
    with pytest.raises(ToolError) as caught:
        loaded.call(
            "controller_run_sql", sql="INSERT INTO items (id, name) VALUES ('x', 'x')"
        )
    assert caught.value.code == "db_error"
    assert "not authorized" in caught.value.message
    assert caught.value.details and "sqlite_code" in caught.value.details

    with pytest.raises(ToolError, match="no such table"):
        loaded.call("controller_run_sql", sql="SELECT * FROM nope")


def test_run_sql_bad_argument_is_argument_error(loaded):
    with pytest.raises(ArgumentError) as caught:
        loaded.call("controller_run_sql", sql=3)
    assert caught.value.violations[0]["path"] == "sql"
    with pytest.raises(ArgumentError):
        loaded.call("controller_run_sql", sql="SELECT 1", extra=True)


def test_run_sql_blob_is_base64(loaded):
    loaded.db.execute("UPDATE items SET payload = ? WHERE id = 'i1'", b"\x00\x01")
    rows = loaded.call(
        "controller_run_sql", sql="SELECT payload FROM items WHERE id = 'i1'"
    )["rows"]
    assert rows == [["AAE="]]


def test_changes_after_two_calls(loaded):
    loaded.call("add_item", name="one")
    loaded.call("finish_item", item_id="i1")
    reported = loaded.call("controller_changes")
    assert sorted(c["op"] for c in reported) == ["insert", "update"]
    assert reported == [c.to_dict() for c in loaded.changes()]


def test_digest_matches_instance_digest(loaded):
    assert loaded.call("controller_digest") == loaded.digest()
    loaded.call("add_item", name="moved")
    assert loaded.call("controller_digest") == loaded.digest()


def test_all_three_absent_from_tools(loaded):
    listed = {tool["name"] for tool in loaded.tools()}
    assert listed.isdisjoint(
        {"controller_run_sql", "controller_changes", "controller_digest"}
    )
    assert {"controller_run_sql", "controller_changes", "controller_digest"} <= set(
        loaded.world.tools
    )


def test_registering_control_name_fails(toy_world):
    for name in ("controller_run_sql", "controller_changes", "controller_digest"):
        with pytest.raises(WorldBug, match="reserved"):

            @toy_world.tool(name=name)
            def mine(ctx: Ctx) -> None:
                """Clash."""


def test_control_bypasses_middleware(loaded, seen):
    seen.clear()
    loaded.call("controller_digest")
    assert seen == []
    loaded.call("add_item", name="seen")
    assert seen == ["add_item"]


def test_control_function_outside_dispatch_is_a_world_bug(loaded):
    with pytest.raises(WorldBug, match=r"outside control\.dispatch"):
        controller_digest(loaded.ctx)
