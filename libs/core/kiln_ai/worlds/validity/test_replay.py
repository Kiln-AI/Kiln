from __future__ import annotations

import json

from .conftest import (
    FIXED_NOW,
    assistant_message,
    episode,
    error_result,
    tool_call,
    tool_message,
)
from .idmap import IdMap
from .replay import (
    Mismatch,
    argument_ids,
    replay_all,
    replay_episode,
    undeclared_classes,
)
from .scrub import Declared, ScrubRules

CREATE_TOOLS = frozenset({"create_note"})
REAL_A = "11111111-1111-4111-8111-111111111111"
REAL_B = "33333333-3333-4333-8333-333333333333"

RULES = ScrubRules(
    placeholder_fields=frozenset({"created_at"}),
    ignored_fields=frozenset({"updated_at"}),
    free_text_fields=frozenset(),
    id_fields=frozenset({"id"}),
    transport_codes=frozenset({"upstream_error", "rate_limited"}),
    declared={},
)

NOTE_BASE = {
    "id": "n1",
    "text": "first",
    "done": 0,
    "created_at": "2020-01-01T00:00:00Z",
    "epoch": 1,
}
NOTE_N1 = {**NOTE_BASE, "updated_at": "whenever"}


def run(world, fixture, recorded, rules=RULES, served=None, **kwargs):
    return replay_episode(
        world,
        fixture,
        recorded,
        rules,
        IdMap(CREATE_TOOLS),
        served_tools=served
        if served is not None
        else frozenset(
            {"create_note", "get_note", "list_notes", "finish_note", "delete_note"}
        ),
        **kwargs,
    )


def test_replay_matching_episode_has_no_mismatches(notes_world, notes_fixture):
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", NOTE_N1),
    )
    replayed = run(notes_world, notes_fixture, recorded)
    assert replayed.mismatches == []
    assert replayed.divergent_steps == frozenset()
    assert [record["kind"] for record in replayed.records] == ["ok"]
    assert replayed.results[0]["created_at"] == FIXED_NOW


def test_replay_maps_created_ids_by_order(notes_world, notes_fixture):
    recorded = episode(
        assistant_message(tool_call("c1", "create_note", text="second")),
        tool_message(
            "c1",
            {
                "id": REAL_A,
                "text": "second",
                "done": 0,
                "created_at": "2020-01-01T00:00:00Z",
                "epoch": 1,
            },
        ),
        assistant_message(tool_call("c2", "finish_note", note_id=REAL_A)),
        tool_message(
            "c2",
            {
                "id": REAL_A,
                "text": "second",
                "done": 1,
                "created_at": "2020-01-01T00:00:00Z",
                "epoch": 1,
            },
        ),
    )
    replayed = run(notes_world, notes_fixture, recorded)
    assert replayed.mismatches == []
    assert len(replayed.id_pairs) == 1
    recorded_id, world_id = replayed.id_pairs[0]
    assert recorded_id == REAL_A and world_id != REAL_A
    # the results come back in recorded-id space, so the decision step can substitute them
    assert replayed.results[1]["id"] == REAL_A


def test_replay_ambiguous_parallel_creates_flagged(notes_world, notes_fixture):
    created = {
        "text": "x",
        "done": 0,
        "created_at": "2020-01-01T00:00:00Z",
        "epoch": 1,
    }
    recorded = episode(
        assistant_message(
            tool_call("c1", "create_note", text="x"),
            tool_call("c2", "create_note", text="x"),
        ),
        tool_message("c1", {"id": REAL_A, **created}),
        tool_message("c2", {"id": REAL_B, **created}),
    )
    replayed = run(notes_world, notes_fixture, recorded)
    assert [m.kind for m in replayed.mismatches] == ["ambiguous_id", "ambiguous_id"]
    assert replayed.divergent_steps == frozenset()
    assert len(replayed.id_pairs) == 2


def test_replay_declared_divergence_not_a_mismatch(notes_world, notes_fixture):
    rules = ScrubRules(
        placeholder_fields=frozenset({"created_at"}),
        ignored_fields=frozenset({"updated_at"}),
        free_text_fields=frozenset(),
        id_fields=frozenset({"id"}),
        transport_codes=frozenset(),
        declared={
            "get_note": (Declared("epoch_bump", "eventual_consistency", ("/epoch",)),)
        },
    )
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", {**NOTE_N1, "epoch": 99}),
    )
    replayed = run(notes_world, notes_fixture, recorded, rules=rules)
    assert [m.kind for m in replayed.mismatches] == ["declared"]
    assert replayed.mismatches[0].declared == ("epoch_bump",)
    assert replayed.divergent_steps == frozenset()
    assert undeclared_classes(replayed.mismatches) == []


def test_replay_divergent_steps_exclude_declared(notes_world, notes_fixture):
    rules = ScrubRules(
        placeholder_fields=frozenset({"created_at"}),
        ignored_fields=frozenset(),
        free_text_fields=frozenset(),
        id_fields=frozenset({"id"}),
        transport_codes=frozenset(),
        declared={"get_note": (Declared("epoch_bump", "shape", ("/epoch",)),)},
    )
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", {**NOTE_BASE, "epoch": 99}),
        assistant_message(tool_call("c2", "get_note", note_id="n1")),
        tool_message("c2", {**NOTE_BASE, "text": "different"}),
    )
    replayed = run(notes_world, notes_fixture, recorded, rules=rules)
    assert [m.kind for m in replayed.mismatches] == ["declared", "mismatch"]
    assert replayed.divergent_steps == frozenset({1})
    assert undeclared_classes(replayed.mismatches) == [("get_note", "/text")]


def test_replay_error_envelope_code_mismatch(notes_world, notes_fixture):
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="missing")),
        tool_message("c1", error_result("permission_denied", "no"), is_error=False),
    )
    replayed = run(notes_world, notes_fixture, recorded)
    assert [m.kind for m in replayed.mismatches] == ["error_code"]
    assert replayed.mismatches[0].replayed["error"]["code"] == "not_found"
    assert ("get_note", "/error/code") in undeclared_classes(replayed.mismatches)


def test_replay_unserved_tool_skipped_and_counted(notes_world, notes_fixture):
    recorded = episode(
        assistant_message(tool_call("c1", "bulk_delete_notes", project="x")),
        tool_message("c1", error_result("permission_denied")),
    )
    replayed = run(notes_world, notes_fixture, recorded, served=frozenset({"get_note"}))
    assert [m.kind for m in replayed.mismatches] == ["unserved"]
    assert replayed.results == [None]
    assert replayed.skipped_steps == frozenset({0})
    assert undeclared_classes(replayed.mismatches) == []


def test_replay_transport_code_excluded_to_caveats(notes_world, notes_fixture):
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", error_result("upstream_error"), is_error=True),
    )
    replayed = run(notes_world, notes_fixture, recorded)
    assert [m.kind for m in replayed.mismatches] == ["transport"]
    assert replayed.results == [None]
    assert replayed.skipped_steps == frozenset({0})


def test_replay_result_id_presence_only_unless_used_later(notes_world, notes_fixture):
    """A server-minted id in a result is noise until the episode uses it."""
    unused = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", {**NOTE_N1, "id": REAL_A}),
    )
    assert run(notes_world, notes_fixture, unused).mismatches == []

    used = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", {**NOTE_N1, "id": REAL_A}),
        assistant_message(tool_call("c2", "finish_note", note_id=REAL_A)),
        tool_message("c2", {**NOTE_N1, "id": REAL_A, "done": 1}),
    )
    replayed = run(notes_world, notes_fixture, used)
    assert replayed.mismatches[0].kind == "mismatch"
    assert [d.path for d in replayed.mismatches[0].diffs] == ["/id"]


def test_replay_unknown_id_reported_not_gating(notes_world, notes_fixture):
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", NOTE_N1),
    )
    replayed = run(notes_world, notes_fixture, recorded, known_ids=frozenset({REAL_A}))
    assert replayed.mismatches == []

    with_unknown = episode(
        assistant_message(tool_call("c1", "get_note", note_id=REAL_B)),
        tool_message(
            "c1", error_result("not_found", f"no note {REAL_B}", {"id": REAL_B})
        ),
    )
    flagged = run(
        notes_world, notes_fixture, with_unknown, known_ids=frozenset({REAL_A})
    )
    assert [m.kind for m in flagged.mismatches] == ["unknown_id"]
    assert flagged.records[0]["unknown_ids"] == [REAL_B]
    assert undeclared_classes(flagged.mismatches) == []


def test_replay_null_result_matches(notes_world, notes_fixture):
    """A delete answers null on both arms; the world's `null` is a result, not a skip."""
    recorded = episode(
        assistant_message(tool_call("c1", "delete_note", note_id="n1")),
        tool_message("c1", None),
    )
    replayed = run(notes_world, notes_fixture, recorded)
    assert replayed.mismatches == []
    assert replayed.results == [None]
    assert replayed.skipped_steps == frozenset()


def test_argument_ids_only_looks_forward():
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id=REAL_A)),
        tool_message("c1", {"id": REAL_A}),
        assistant_message(tool_call("c2", "finish_note", note_id=REAL_B)),
        tool_message("c2", {"id": REAL_B}),
    )
    assert argument_ids(recorded, 0) == frozenset({REAL_B})
    assert argument_ids(recorded, 1) == frozenset()


def test_undeclared_classes_dedupes_by_signature():
    def mismatch(index: int, path: str, kind: str = "mismatch") -> Mismatch:
        return Mismatch(
            run_id="r",
            configuration="A",
            step_index=index,
            tool_name="list_notes",
            arguments={},
            recorded=None,
            replayed=None,
            diffs=[],
            kind=kind,  # type: ignore[arg-type]
            declared=(),
            classes=(("list_notes", path),),
        )

    classes = undeclared_classes(
        [
            mismatch(0, "/results/*/state"),
            mismatch(1, "/results/*/state"),
            mismatch(2, "/count"),
            mismatch(3, "/ignored", kind="declared"),
        ]
    )
    assert classes == [("list_notes", "/count"), ("list_notes", "/results/*/state")]


def test_replay_writes_jsonl_line_per_step_with_schema_version(
    notes_world, notes_fixture, tmp_path
):
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", NOTE_N1),
        assistant_message(tool_call("c2", "list_notes")),
        tool_message("c2", {"results": [NOTE_N1], "count": 1}),
    )
    out = tmp_path / "runs" / "replay.jsonl"
    replayed = replay_all(
        notes_world,
        notes_fixture,
        [recorded],
        RULES,
        create_tools=CREATE_TOOLS,
        served_tools=frozenset({"get_note", "list_notes"}),
        out=out,
    )
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(lines) == 2
    assert {line["schema_version"] for line in lines} == {1}
    assert [line["kind"] for line in lines] == ["ok", "ok"]
    assert lines[0]["run_id"] == "run-1"
    assert lines[0]["input_no"] == 1
    assert lines[0]["half"] == "tuning"
    assert lines[1]["tool_name"] == "list_notes"
    assert replayed[0].mismatches == []
