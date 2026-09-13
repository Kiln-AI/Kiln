from __future__ import annotations

import base64
import sys

import pytest

from .conftest import build_toy_world
from .errors import ToolError
from .instances import BASELINE_NAME
from .world import World

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


def as_dicts(instance) -> list[dict]:
    return [change.to_dict() for change in instance.changes()]


@pytest.fixture
def loaded(toy_world, frozen):
    instance = toy_world.instance("base")
    try:
        yield instance
    finally:
        instance.destroy()


def test_insert_update_delete_single_and_composite_keys(loaded):
    loaded.db.execute("INSERT INTO items (id, name) VALUES ('new', 'inserted')")
    loaded.db.execute("UPDATE items SET name = 'renamed' WHERE id = 'i2'")
    loaded.db.execute("DELETE FROM items WHERE id = 'i1'")
    loaded.db.execute("INSERT INTO tags (item_id, tag) VALUES ('i2', 'blue')")
    loaded.db.execute("DELETE FROM tags WHERE item_id = 'i1' AND tag = 'red'")

    by_table: dict[str, list[dict]] = {}
    for change in as_dicts(loaded):
        by_table.setdefault(change["table"], []).append(change)

    assert [c["op"] for c in by_table["items"]] == ["delete", "update", "insert"]
    assert by_table["items"][0]["key"] == {"id": "i1"}
    assert by_table["items"][1]["after"] == {"id": "i2", "name": "renamed"}
    assert by_table["items"][2]["before"] is None

    assert [(c["op"], c["key"]) for c in by_table["tags"]] == [
        ("delete", {"item_id": "i1", "tag": "red"}),
        ("insert", {"item_id": "i2", "tag": "blue"}),
    ]


def test_update_carries_only_changed_columns_plus_key(loaded):
    loaded.db.execute("UPDATE items SET done = 1 WHERE id = 'i2'")
    change = as_dicts(loaded)[0]
    assert change["before"] == {"id": "i2", "done": 0}
    assert change["after"] == {"id": "i2", "done": 1}


def test_null_safe_comparison_null_to_value_and_back(loaded):
    loaded.db.execute("UPDATE items SET note = 'now set' WHERE id = 'i1'")
    loaded.db.execute("UPDATE items SET note = NULL WHERE id = 'i2'")
    changes = {c["key"]["id"]: c for c in as_dicts(loaded)}
    assert changes["i1"]["before"] == {"id": "i1", "note": None}
    assert changes["i1"]["after"] == {"id": "i1", "note": "now set"}
    assert changes["i2"]["before"] == {"id": "i2", "note": "noted"}
    assert changes["i2"]["after"] == {"id": "i2", "note": None}


def test_failed_call_leaves_nothing(loaded):
    with pytest.raises(ToolError, match="no item"):
        loaded.call("tag_item", item_id="nope", tag="x")
    assert as_dicts(loaded) == []


def test_noop_update_records_nothing(loaded):
    loaded.db.execute("UPDATE items SET name = name WHERE id = 'i1'")
    loaded.db.execute("UPDATE items SET note = 'noted' WHERE id = 'i2'")
    assert as_dicts(loaded) == []


def test_insert_then_update_collapses(loaded):
    item = loaded.call("add_item", name="fresh")
    loaded.call("finish_item", item_id=item["id"])
    changes = as_dicts(loaded)
    assert len(changes) == 1
    assert changes[0]["op"] == "insert"
    assert changes[0]["after"]["done"] == 1


def test_hook_rows_absent_baseline_copy_taken(tmp_path):
    world = build_toy_world(tmp_path, with_hook=True)
    instance = world.instance(None, owner="ada")
    try:
        assert (instance.dir / BASELINE_NAME).is_file()
        assert as_dicts(instance) == []
        instance.call("add_item", name="agent")
        names = [c["after"]["name"] for c in as_dicts(instance)]
        assert names == ["agent"]
    finally:
        instance.destroy()


def test_no_hooks_fixture_file_is_baseline_no_copy(toy_world, frozen, loaded):
    assert not (loaded.dir / BASELINE_NAME).exists()
    assert as_dicts(loaded) == []


def test_untracked_table_absent(loaded):
    loaded.call("add_item", name="counts")
    assert loaded.db.one("SELECT n FROM counters WHERE name = 'adds'")["n"] == 1
    assert {c["table"] for c in as_dicts(loaded)} == {"items"}
    before = loaded.digest()
    loaded.db.execute("UPDATE counters SET n = 99 WHERE name = 'adds'")
    assert loaded.digest() == before


def test_ordering_table_then_key_tuple_mixed_types(tmp_path):
    """Records come out ordered by table name, then by key in SQLite's storage-class order.
    The key column is deliberately untyped so one table holds integers, reals, text and a
    blob; NOT NULL is required of every tracked key (see test_world.py)."""
    schema = """
    CREATE TABLE mixed (k ANY NOT NULL PRIMARY KEY, v TEXT) ;
    CREATE TABLE zebra (id TEXT PRIMARY KEY) STRICT;
    """
    world = World(
        "mixed", "1", schema, fixtures_dir=tmp_path / "f", work_dir=tmp_path / "w"
    )
    instance = world.instance(None)
    try:
        instance.db.execute("INSERT INTO zebra (id) VALUES ('z')")
        instance.db.executemany(
            "INSERT INTO mixed (k, v) VALUES (?, ?)",
            [("text", "s"), (2, "i"), (b"\x00", "b"), (1.5, "f")],
        )
        keys = [c["key"]["k"] for c in as_dicts(instance) if c["table"] == "mixed"]
        assert keys == [1.5, 2, "text", base64.b64encode(b"\x00").decode()]
        assert [c["table"] for c in as_dicts(instance)] == [
            "mixed",
            "mixed",
            "mixed",
            "mixed",
            "zebra",
        ]
    finally:
        instance.destroy()


def test_blob_base64(loaded):
    loaded.db.execute("UPDATE items SET payload = ? WHERE id = 'i1'", b"\x00\x01\xfe")
    change = as_dicts(loaded)[0]
    assert change["after"]["payload"] == base64.b64encode(b"\x00\x01\xfe").decode()


def test_cumulative_across_calls(loaded):
    loaded.call("add_item", name="one")
    assert len(as_dicts(loaded)) == 1
    loaded.call("add_item", name="two")
    assert len(as_dicts(loaded)) == 2
    loaded.call("finish_item", item_id="i1")
    assert len(as_dicts(loaded)) == 3


def test_digest_changes_on_any_row_and_stable_on_none(loaded):
    before = loaded.digest()
    assert loaded.digest() == before
    loaded.db.execute("UPDATE items SET done = 1 WHERE id = 'i1'")
    after = loaded.digest()
    assert after != before
    loaded.db.execute("UPDATE items SET done = 0 WHERE id = 'i1'")
    assert loaded.digest() == before


def test_digest_includes_schema_hash(toy_world, frozen, loaded):
    from .changes import digest

    baseline = loaded.digest()
    assert digest(loaded.inspect(), toy_world.tracked_tables, "other-hash") != baseline


def test_changes_and_digest_survive_destroy_order(toy_world, frozen):
    instance = toy_world.instance("base")
    instance.call("add_item", name="x")
    snapshot = as_dicts(instance)
    instance.destroy()
    assert len(snapshot) == 1
