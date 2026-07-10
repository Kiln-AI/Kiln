from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.provenance import (
    NOTES_MAX_LENGTH,
    KilnArtifactProvenance,
    validate_derived_from_ids,
)

LOAD_CONTEXT = {"loading_from_file": True}


def load(data: dict) -> KilnArtifactProvenance:
    """Validate provenance under the lenient load-from-file context."""
    return KilnArtifactProvenance.model_validate(data, context=LOAD_CONTEXT)


# ---- notes ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  hello  ", "hello"),
        ("hello", "hello"),
        ("", None),
        ("   ", None),
        ("\n\t ", None),
        (None, None),
    ],
)
def test_notes_create_coercion(raw, expected):
    assert KilnArtifactProvenance(origin="human", notes=raw).notes == expected


def test_notes_create_at_cap_ok():
    note = "x" * NOTES_MAX_LENGTH
    assert KilnArtifactProvenance(origin="human", notes=note).notes == note


def test_notes_create_over_cap_raises():
    with pytest.raises(ValidationError, match="notes must be <="):
        KilnArtifactProvenance(origin="human", notes="x" * (NOTES_MAX_LENGTH + 1))


def test_notes_cap_measured_after_strip():
    # 2000 core chars plus surrounding whitespace is accepted (measured after strip).
    note = "  " + ("x" * NOTES_MAX_LENGTH) + "  "
    assert (
        KilnArtifactProvenance(origin="human", notes=note).notes
        == "x" * NOTES_MAX_LENGTH
    )


def test_notes_load_over_cap_accepted_and_stripped():
    long_note = "x" * 3000
    result = load({"origin": "human", "notes": "  " + long_note + "  "})
    assert result.notes == long_note


# ---- derived_from_ids ----


def test_derived_from_ids_create_valid():
    p = KilnArtifactProvenance(origin="human", derived_from_ids=["a1", "b2", "c3"])
    assert p.derived_from_ids == ["a1", "b2", "c3"]


def test_derived_from_ids_create_empty_ok():
    assert KilnArtifactProvenance(origin="human").derived_from_ids == []


@pytest.mark.parametrize(
    "bad_list",
    [
        [None],
        [""],
        ["   "],
        ["ok", ""],
        ["ok", None],
    ],
)
def test_derived_from_ids_create_rejects_empty_entries(bad_list):
    with pytest.raises(ValidationError, match="non-empty ids"):
        KilnArtifactProvenance(origin="human", derived_from_ids=bad_list)


def test_derived_from_ids_create_rejects_duplicates():
    with pytest.raises(ValidationError, match="duplicate id"):
        KilnArtifactProvenance(origin="human", derived_from_ids=["a1", "a1"])


def test_derived_from_ids_load_accepts_imperfect_list_as_is():
    dirty = ["a1", "a1", "", None]
    result = load({"origin": "human", "derived_from_ids": dirty})
    assert result.derived_from_ids == dirty


# ---- origin ----


@pytest.mark.parametrize("origin", ["human", "agent"])
def test_origin_create_valid(origin):
    assert KilnArtifactProvenance(origin=origin).origin == origin


@pytest.mark.parametrize("origin", [None, "", "banana", "Human", "HUMAN", "user"])
def test_origin_create_invalid_raises(origin):
    with pytest.raises(ValidationError, match="origin is required"):
        KilnArtifactProvenance(origin=origin)


@pytest.mark.parametrize("origin", [None, "banana", "human", "agent", "user"])
def test_origin_load_accepts_anything(origin):
    assert load({"origin": origin}).origin == origin


def test_origin_absent_on_load_defaults_to_none():
    # A file whose provenance object omits the origin key must still load
    # (validate_default must not break lenient-on-load back-compat).
    result = load({"notes": "legacy note"})
    assert result.origin is None


# ---- whole object ----


def test_full_object_create():
    p = KilnArtifactProvenance(
        notes="  a note  ",
        derived_from_ids=["parent1"],
        origin="agent",
    )
    assert p.notes == "a note"
    assert p.derived_from_ids == ["parent1"]
    assert p.origin == "agent"


def test_create_without_origin_raises():
    with pytest.raises(ValidationError, match="origin is required"):
        KilnArtifactProvenance(notes="valid", derived_from_ids=["a1"])


def test_round_trip_dump_and_reload():
    original = KilnArtifactProvenance(
        notes="round trip", derived_from_ids=["p1", "p2"], origin="human"
    )
    reloaded = load(original.model_dump())
    assert reloaded == original


def test_load_ignores_unknown_extra_keys():
    result = load({"origin": "human", "future_field": "some value"})
    assert result.origin == "human"
    assert not hasattr(result, "future_field")


# ---- validate_derived_from_ids helper ----


def test_helper_none_provenance_no_raise():
    sibling_exists = Mock()
    validate_derived_from_ids(None, "self-id", sibling_exists)
    sibling_exists.assert_not_called()


def test_helper_empty_derived_from_ids_no_raise():
    sibling_exists = Mock(return_value=False)
    p = KilnArtifactProvenance(origin="human")
    validate_derived_from_ids(p, "self-id", sibling_exists)
    sibling_exists.assert_not_called()


def test_helper_all_known_ids_no_raise():
    p = KilnArtifactProvenance(origin="human", derived_from_ids=["a1", "b2"])
    validate_derived_from_ids(p, "self-id", lambda _cid: True)


def test_helper_unknown_id_raises():
    p = KilnArtifactProvenance(origin="human", derived_from_ids=["a1", "missing"])
    known = {"a1"}
    with pytest.raises(ValueError, match="unknown sibling: missing"):
        validate_derived_from_ids(p, "self-id", lambda cid: cid in known)


def test_helper_self_reference_raises():
    p = KilnArtifactProvenance(origin="human", derived_from_ids=["self-id"])
    sibling_exists = Mock(return_value=True)
    with pytest.raises(ValueError, match="cannot reference this artifact itself"):
        validate_derived_from_ids(p, "self-id", sibling_exists)
    # Self-reference is detected before the existence check.
    sibling_exists.assert_not_called()
