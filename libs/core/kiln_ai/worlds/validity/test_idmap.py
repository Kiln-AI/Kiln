from __future__ import annotations

import pytest

from .idmap import IdMap, IdMapConflict, created_id, known_ids

REAL_A = "11111111-1111-4111-8111-111111111111"
WORLD_A = "22222222-2222-4222-8222-222222222222"
REAL_B = "33333333-3333-4333-8333-333333333333"
WORLD_B = "44444444-4444-4444-8444-444444444444"
FIXTURE = "55555555-5555-4555-8555-555555555555"

CREATE_TOOLS = frozenset({"create_note", "create_comment"})


def test_created_id_only_for_configured_create_tools():
    assert created_id("create_note", {"id": REAL_A}, CREATE_TOOLS) == REAL_A
    assert created_id("get_note", {"id": REAL_A}, CREATE_TOOLS) is None
    assert created_id("create_note", {"no_id": 1}, CREATE_TOOLS) is None
    assert created_id("create_note", None, CREATE_TOOLS) is None
    assert created_id("create_note", {"id": None}, CREATE_TOOLS) is None


def test_idmap_records_pairs_and_rewrites_nested_args():
    id_map = IdMap(CREATE_TOOLS)
    id_map.record(REAL_A, WORLD_A)
    id_map.record(REAL_B, WORLD_B)
    arguments = {
        "note_id": REAL_A,
        "related": [REAL_B, "not-an-id"],
        "nested": {"parent": REAL_A},
    }
    assert id_map.to_world(arguments) == {
        "note_id": WORLD_A,
        "related": [WORLD_B, "not-an-id"],
        "nested": {"parent": WORLD_A},
    }
    assert id_map.pairs == [(REAL_A, WORLD_A), (REAL_B, WORLD_B)]


def test_to_recorded_is_inverse_of_to_world():
    id_map = IdMap(CREATE_TOOLS)
    id_map.record(REAL_A, WORLD_A)
    value = {"results": [{"id": REAL_A, "text": "keep"}]}
    assert id_map.to_recorded(id_map.to_world(value)) == value


def test_idmap_conflict_raises():
    id_map = IdMap(CREATE_TOOLS)
    id_map.record(REAL_A, WORLD_A)
    id_map.record(REAL_A, WORLD_A)  # idempotent
    with pytest.raises(IdMapConflict, match="already maps to"):
        id_map.record(REAL_A, WORLD_B)
    with pytest.raises(IdMapConflict, match="already maps back"):
        id_map.record(REAL_B, WORLD_A)


def test_idmap_unknown_ids_excludes_fixture_ids():
    id_map = IdMap(CREATE_TOOLS)
    id_map.record(REAL_A, WORLD_A)
    unknown = id_map.unknown_ids(
        {"a": REAL_A, "b": FIXTURE, "c": REAL_B, "d": "plain"},
        known=frozenset({FIXTURE}),
    )
    assert unknown == [REAL_B]


def test_known_ids_collects_every_uuid_in_an_export():
    assert known_ids([{"rows": [{"id": FIXTURE}, {"id": FIXTURE}]}]) == frozenset(
        {FIXTURE}
    )
