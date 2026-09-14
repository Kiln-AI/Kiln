from __future__ import annotations

import json

import pytest

from .scrub import (
    MISSING,
    PRESENT,
    Declared,
    Diff,
    ScrubRules,
    compare,
    declared_from_evidence,
    is_declared,
    normalize_arguments,
    path_signature,
    scrub,
)


def rules(**overrides) -> ScrubRules:
    base = {
        "placeholder_fields": frozenset({"created_at", "epoch"}),
        "ignored_fields": frozenset({"updated_at"}),
        "free_text_fields": frozenset({"comment"}),
        "id_fields": frozenset({"id"}),
        "transport_codes": frozenset({"upstream_error"}),
        "declared": {},
    }
    base.update(overrides)
    return ScrubRules(**base)  # type: ignore[arg-type]


def test_scrub_rules_default_is_empty():
    default = ScrubRules.default()
    assert default.placeholder_fields == frozenset()
    assert default.ignored_fields == frozenset()
    assert default.free_text_fields == frozenset()
    assert default.id_fields == frozenset()
    assert default.transport_codes == frozenset()
    assert default.declared == {}


def test_scrub_placeholder_fields_compare_present_or_null():
    recorded = {"created_at": "2026-01-01T00:00:00Z", "epoch": 17}
    replayed = {"created_at": "2026-03-04T05:06:07Z", "epoch": 2}
    assert compare(recorded, replayed, rules()) == []
    assert scrub(recorded, rules()) == {"created_at": PRESENT, "epoch": PRESENT}
    # present against null is a difference: the world did not stamp what the system did
    diffs = compare(recorded, {"created_at": None, "epoch": 2}, rules())
    assert [(d.path, d.recorded, d.replayed) for d in diffs] == [
        ("/created_at", PRESENT, None)
    ]


def test_scrub_ignored_field_dropped_at_any_depth():
    value = {"updated_at": 1, "results": [{"updated_at": 2, "name": "a"}]}
    assert scrub(value, rules()) == {"results": [{"name": "a"}]}
    assert compare(value, {"results": [{"name": "a"}]}, rules()) == []


def test_compare_reports_json_pointer_paths():
    diffs = compare(
        {"results": [{"state": "todo"}, {"state": "done"}]},
        {"results": [{"state": "todo"}, {"state": "started"}]},
        rules(),
    )
    assert [(d.path, d.recorded, d.replayed) for d in diffs] == [
        ("/results/1/state", "done", "started")
    ]


def test_compare_list_length_mismatch_reported_at_list_path():
    diffs = compare({"results": [1, 2, 3]}, {"results": [1, 2]}, rules())
    assert [(d.path, d.recorded, d.replayed) for d in diffs] == [("/results", 3, 2)]


def test_compare_list_length_mismatch_still_compares_the_common_prefix():
    diffs = compare({"results": [1, 9, 3]}, {"results": [1, 2]}, rules())
    assert [d.path for d in diffs] == ["/results", "/results/1"]


def test_compare_missing_key_reported():
    diffs = compare({"a": 1}, {"b": 2}, rules())
    assert sorted((d.path, d.recorded, d.replayed) for d in diffs) == [
        ("/a", 1, MISSING),
        ("/b", MISSING, 2),
    ]


def test_compare_id_fields_presence_only_unless_exact():
    recorded = {"id": "aaa", "name": "n"}
    replayed = {"id": "bbb", "name": "n"}
    assert compare(recorded, replayed, rules()) == []
    diffs = compare(recorded, replayed, rules(), exact_ids=frozenset({"aaa"}))
    assert [(d.path, d.recorded, d.replayed) for d in diffs] == [("/id", "aaa", "bbb")]


def test_compare_id_field_null_on_one_side_is_a_difference():
    diffs = compare({"id": "aaa"}, {"id": None}, rules())
    assert [d.path for d in diffs] == ["/id"]


def test_compare_id_field_must_be_a_string_on_both_sides():
    """Presence-only means the *value* is minted by whoever answered, not that the field
    may be any shape at all."""
    assert [d.path for d in compare({"id": "abc"}, {"id": 123}, rules())] == ["/id"]
    assert compare({"id": ""}, {"id": "abc"}, rules()) == []


def test_compare_id_key_holding_a_structure_is_still_compared():
    """The id rule is for leaves. An `id` holding a list or an object is structure the
    world has to reproduce, and taking the presence branch would blind the whole subtree."""
    assert [d.path for d in compare({"id": ["a"]}, {"id": ["a", "b"]}, rules())] == [
        "/id"
    ]
    assert [d.path for d in compare({"id": {"x": 1}}, {"id": {"x": 2}}, rules())] == [
        "/id/x"
    ]


def test_diff_signature_keeps_numeric_object_keys_apart():
    """A list index collapses to `*`; an object key that happens to be a number does not,
    because `/by_year/2026/total` and `/by_year/2027/total` are different fields."""
    diffs = compare(
        {"by_year": {"2026": 1}, "results": [{"state": "a"}]},
        {"by_year": {"2026": 2}, "results": [{"state": "b"}]},
        rules(),
    )
    signatures = {d.path: d.divergence_signature for d in diffs}
    assert signatures == {
        "/by_year/2026": "/by_year/2026",
        "/results/0/state": "/results/*/state",
    }
    # the pointer-only fallback cannot tell the two apart, and says so
    assert path_signature("/by_year/2026") == "/by_year/*"


def test_path_signature_replaces_indices():
    assert path_signature("/results/3/state") == "/results/*/state"
    assert path_signature("/results/0") == "/results/*"
    assert path_signature("/updated_at") == "/updated_at"


def test_normalize_arguments_free_text_by_type():
    normalized = normalize_arguments(
        {"comment": "Please review this", "state": "todo", "updated_at": "x"}, rules()
    )
    assert normalized == {"comment": "string", "state": "todo"}
    assert normalize_arguments({"comment": None}, rules()) == {"comment": "null"}


def test_scrub_rules_from_file_reads_scrub_section(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "schema_version: 1\n"
        "scrub:\n"
        "  placeholder_fields: [created_at]\n"
        "  ignored_fields: [updated_at]\n"
        "  transport_codes: [upstream_error, rate_limited]\n",
        encoding="utf-8",
    )
    loaded = ScrubRules.from_file(path)
    assert loaded.placeholder_fields == frozenset({"created_at"})
    assert loaded.transport_codes == frozenset({"upstream_error", "rate_limited"})
    assert loaded.free_text_fields == frozenset()


def test_scrub_rules_from_file_rejects_unknown_key(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("scrub:\n  placeholder_field: [created_at]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown scrub keys"):
        ScrubRules.from_file(path)


def test_scrub_rules_from_file_requires_a_scrub_section(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("schema_version: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no 'scrub' section"):
        ScrubRules.from_file(path)


EVIDENCE = {
    "schema_version": 1,
    "divergences": [
        {
            "id": "updated_at_single_bump",
            "kind": "eventual_consistency",
            "tools": ["update_note"],
            "fields": ["/updated_at", "/results/*/updated_at"],
        },
        {
            "id": "no_rate_limit",
            "kind": "rate_limit_timing",
            "tools": ["*"],
            "fields": ["/error/code"],
        },
    ],
}


def test_declared_from_evidence_expands_star_and_requires_fields():
    declared = declared_from_evidence(EVIDENCE, ["update_note", "get_note"])
    assert {entry.id for entry in declared["get_note"]} == {"no_rate_limit"}
    assert {entry.id for entry in declared["update_note"]} == {
        "updated_at_single_bump",
        "no_rate_limit",
    }

    broken = json.loads(json.dumps(EVIDENCE))
    del broken["divergences"][0]["fields"]
    with pytest.raises(ValueError, match="has no 'fields'"):
        declared_from_evidence(broken, ["update_note"])


def test_declared_from_evidence_requires_the_divergences_list():
    with pytest.raises(ValueError, match="no 'divergences' list"):
        declared_from_evidence({"schema_version": 1}, ["a"])


def test_declared_from_evidence_requires_tools():
    """An entry that names no tool declares nothing, and a module that raises for a
    missing `fields` must not shrug at a missing `tools`."""
    with pytest.raises(ValueError, match="has no 'tools'"):
        declared_from_evidence(
            {"divergences": [{"id": "x", "kind": "k", "fields": ["/a"]}]}, ["a"]
        )
    with pytest.raises(ValueError, match="non-empty list"):
        declared_from_evidence(
            {"divergences": [{"id": "x", "kind": "k", "tools": [], "fields": ["/a"]}]},
            ["a"],
        )


def test_is_declared_requires_every_diff_covered():
    declared = declared_from_evidence(EVIDENCE, ["update_note"])
    with_declared = rules().with_declared(declared)
    covered = [Diff("/results/2/updated_at", 1, 2)]
    assert is_declared("update_note", covered, with_declared) == (
        "updated_at_single_bump",
    )
    mixed = [Diff("/results/2/updated_at", 1, 2), Diff("/results/2/state", "a", "b")]
    assert is_declared("update_note", mixed, with_declared) == ()
    assert is_declared("get_note", covered, with_declared) == ()


def test_is_declared_covers_prefix_pointer():
    with_declared = rules().with_declared(
        {"list_notes": (Declared("pagination", "shape", ("/extra_stats",)),)}
    )
    diffs = [Diff("/extra_stats/total/0", 1, 2)]
    assert is_declared("list_notes", diffs, with_declared) == ("pagination",)
    assert is_declared("list_notes", [Diff("/extra_statsx", 1, 2)], with_declared) == ()
