from typing import Mapping

import pytest

from kiln_ai.adapters.model_agent_info import (
    BANNED_NOTE_WORDS,
    MAX_NOTE_CHARS,
    MAX_TAGS_PER_ENTRY,
    MODEL_NOTE_LABELS,
    MODEL_TAGS,
    PROVIDER_ENTRY_TAGS,
    PROVIDER_LIST_TAGS,
    PROVIDER_NOTE_LABELS,
    TAG_PATTERN,
    TagInfo,
    TagKind,
)


def assert_valid_tags(tags: list[str], allowed: Mapping[str, TagInfo]) -> None:
    """Assert that tags follow the tag rules of model_agent_info and are all in `allowed`."""
    for tag in tags:
        assert TAG_PATTERN.match(tag), (
            f"Tag {tag!r} does not match {TAG_PATTERN.pattern}"
        )
        assert tag in allowed, (
            f"Tag {tag!r} is not in the allowed tags {sorted(allowed)}"
        )
    duplicates = sorted({tag for tag in tags if tags.count(tag) > 1})
    assert not duplicates, f"Duplicate tags: {duplicates}"
    assert len(tags) <= MAX_TAGS_PER_ENTRY, (
        f"{len(tags)} tags, more than the limit of {MAX_TAGS_PER_ENTRY}"
    )


def assert_valid_note(note: str | None) -> None:
    """Assert that a note is None, or a non-blank string within MAX_NOTE_CHARS."""
    if note is None:
        return
    assert note.strip(), "A note must be None or non-blank text"
    assert len(note) <= MAX_NOTE_CHARS, (
        f"Note has {len(note)} characters, more than the limit of {MAX_NOTE_CHARS}"
    )


def assert_note_format(
    note: str,
    labels: tuple[str, ...],
    required: tuple[str, ...],
) -> None:
    """Assert that a note follows the labeled-line format.

    Args:
        note: The note string (must not be None).
        labels: The allowed labels in required order.
        required: Labels that must be present.
    """
    lines = note.split("\n")
    seen_indices: list[int] = []
    seen_labels: list[str] = []

    for i, line in enumerate(lines):
        matched = False
        for label_idx, label in enumerate(labels):
            if line.startswith(label):
                matched = True
                assert label not in seen_labels, (
                    f"Line {i + 1}: label {label!r} appears more than once"
                )
                if seen_indices:
                    assert label_idx > seen_indices[-1], (
                        f"Line {i + 1}: label {label!r} is out of order"
                        f" (after {seen_labels[-1]!r})"
                    )
                seen_indices.append(label_idx)
                seen_labels.append(label)
                break
        assert matched, (
            f"Line {i + 1}: {line!r} does not start with a known label from {labels}"
        )

    for req in required:
        assert req in seen_labels, f"Required label {req!r} is missing"


ALL_TAG_MAPS = {
    "MODEL_TAGS": MODEL_TAGS,
    "PROVIDER_ENTRY_TAGS": PROVIDER_ENTRY_TAGS,
    "PROVIDER_LIST_TAGS": PROVIDER_LIST_TAGS,
}


@pytest.mark.parametrize(
    "map_name, tag, info",
    [
        pytest.param(map_name, tag, info, id=f"{map_name}-{tag}")
        for map_name, tag_map in ALL_TAG_MAPS.items()
        for tag, info in tag_map.items()
    ],
)
def test_tag_map_entries_are_well_formed(map_name, tag, info):
    assert TAG_PATTERN.match(tag), f"{map_name} key {tag!r} has a bad format"
    assert isinstance(info, TagInfo)
    assert isinstance(info.meaning, str) and info.meaning.strip()
    assert isinstance(info.kind, TagKind)


def test_no_tag_in_multiple_maps():
    all_tags: list[tuple[str, str]] = []
    for map_name, tag_map in ALL_TAG_MAPS.items():
        for tag in tag_map:
            all_tags.append((tag, map_name))
    seen: dict[str, str] = {}
    for tag, map_name in all_tags:
        assert tag not in seen, f"Tag {tag!r} is in both {seen[tag]} and {map_name}"
        seen[tag] = map_name


def test_model_tag_map_has_one_lineage_tag():
    lineage_tags = [
        tag for tag, info in MODEL_TAGS.items() if info.kind == TagKind.lineage
    ]
    assert lineage_tags == ["current"], (
        f"Expected exactly one lineage tag 'current', got {lineage_tags}"
    )
    assert MODEL_TAGS["current"].max_models is None

    for tag, info in MODEL_TAGS.items():
        if info.kind == TagKind.set:
            assert info.max_models is not None and info.max_models >= 1, (
                f"Set tag {tag!r} must have max_models >= 1, got {info.max_models}"
            )


def test_starting_tags():
    # Adding a tag means updating this test too, so the new tag gets reviewed.
    assert set(MODEL_TAGS) == {
        "current",
        "recommended",
        "top_value",
        "top_fast",
        "top_on_device",
        "top_open",
        "top_writing",
    }
    assert MODEL_TAGS["current"].kind == TagKind.lineage
    assert MODEL_TAGS["current"].max_models is None
    assert MODEL_TAGS["recommended"].kind == TagKind.set
    assert MODEL_TAGS["recommended"].max_models == 20
    for tag in ("top_value", "top_fast", "top_on_device", "top_open", "top_writing"):
        assert MODEL_TAGS[tag].kind == TagKind.set
        assert MODEL_TAGS[tag].max_models == 14

    assert dict(PROVIDER_ENTRY_TAGS) == {}
    assert dict(PROVIDER_LIST_TAGS) == {}


def test_note_labels_well_formed():
    for label in MODEL_NOTE_LABELS:
        assert label.endswith(":"), f"Model note label {label!r} does not end with ':'"
    assert len(MODEL_NOTE_LABELS) == len(set(MODEL_NOTE_LABELS)), (
        "Duplicate model note labels"
    )

    for label in PROVIDER_NOTE_LABELS:
        assert label.endswith(":"), (
            f"Provider note label {label!r} does not end with ':'"
        )
    assert len(PROVIDER_NOTE_LABELS) == len(set(PROVIDER_NOTE_LABELS)), (
        "Duplicate provider note labels"
    )


@pytest.mark.parametrize(
    "tags",
    [
        [],
        ["current"],
        ["current", "recommended", "top_value"],
    ],
)
def test_assert_valid_tags_accepts_valid_tags(tags):
    assert_valid_tags(tags, MODEL_TAGS)


@pytest.mark.parametrize(
    "tags, allowed, message",
    [
        (
            ["Best_Value"],
            {"Best_Value": TagInfo("x", TagKind.set, 10)},
            "does not match",
        ),
        (
            ["best-value"],
            {"best-value": TagInfo("x", TagKind.set, 10)},
            "does not match",
        ),
        (
            ["a" * 41],
            {"a" * 41: TagInfo("x", TagKind.set, 10)},
            "does not match",
        ),
        (
            ["top_fast"],
            {"top_value": TagInfo("x", TagKind.set, 14)},
            "not in the allowed tags",
        ),
        (["current", "current"], MODEL_TAGS, "Duplicate tags"),
        (
            [f"tag_{i}" for i in range(MAX_TAGS_PER_ENTRY + 1)],
            {
                f"tag_{i}": TagInfo("x", TagKind.set, 99)
                for i in range(MAX_TAGS_PER_ENTRY + 1)
            },
            "more than the limit",
        ),
    ],
)
def test_assert_valid_tags_rejects_bad_tags(tags, allowed, message):
    with pytest.raises(AssertionError, match=message):
        assert_valid_tags(tags, allowed)


@pytest.mark.parametrize("note", [None, "Good at tool calls.", "x" * MAX_NOTE_CHARS])
def test_assert_valid_note_accepts_valid_notes(note):
    assert_valid_note(note)


@pytest.mark.parametrize(
    "note, message",
    [
        ("", "non-blank"),
        ("  \n\t", "non-blank"),
        ("x" * (MAX_NOTE_CHARS + 1), "more than the limit"),
    ],
)
def test_assert_valid_note_rejects_bad_notes(note, message):
    with pytest.raises(AssertionError, match=message):
        assert_valid_note(note)


class TestAssertNoteFormat:
    def test_valid_model_note(self):
        note = (
            "Description: A fast model.\n"
            "Lineup: Below the large model.\n"
            "Strengths: Good at coding."
        )
        assert_note_format(note, MODEL_NOTE_LABELS, ("Description:", "Lineup:"))

    def test_valid_model_note_all_labels(self):
        note = (
            "Description: Mid-price model.\n"
            "Lineup: Below the flagship.\n"
            "Superseded by: The newer model.\n"
            "Same weights: The fast variant is a faster hosted version.\n"
            "Useful for: Classification.\n"
            "Strengths: Coding.\n"
            "Behavior: Verbose.\n"
            "Deployment: Dense, runs on one GPU."
        )
        assert_note_format(note, MODEL_NOTE_LABELS, ("Description:", "Lineup:"))

    def test_valid_provider_note(self):
        note = (
            "Data retention: No logging by default.\n"
            "Gotchas: Requires account approval."
        )
        assert_note_format(note, PROVIDER_NOTE_LABELS, ())

    def test_rejects_missing_required_label(self):
        note = "Strengths: Good at coding."
        with pytest.raises(
            AssertionError, match=r"Required label.*Description.*missing"
        ):
            assert_note_format(note, MODEL_NOTE_LABELS, ("Description:", "Lineup:"))

    def test_rejects_out_of_order_labels(self):
        note = "Lineup: Below the large model.\nDescription: A fast model."
        with pytest.raises(AssertionError, match="out of order"):
            assert_note_format(note, MODEL_NOTE_LABELS, ("Description:", "Lineup:"))

    def test_rejects_duplicate_label(self):
        note = "Description: First.\nDescription: Second."
        with pytest.raises(AssertionError, match="more than once"):
            assert_note_format(note, MODEL_NOTE_LABELS, ("Description:",))

    def test_rejects_unknown_label(self):
        note = "Unknown: Not a real label."
        with pytest.raises(AssertionError, match="does not start with a known label"):
            assert_note_format(note, MODEL_NOTE_LABELS, ())


def test_banned_note_words_well_formed():
    assert len(BANNED_NOTE_WORDS) >= 1, "BANNED_NOTE_WORDS must not be empty"
    assert len(BANNED_NOTE_WORDS) == len(set(w.lower() for w in BANNED_NOTE_WORDS)), (
        "Duplicate entries in BANNED_NOTE_WORDS"
    )
    for word in BANNED_NOTE_WORDS:
        assert word.strip(), "A banned word must be non-blank"
        assert word == word.lower(), (
            f"Banned word {word!r} should be lowercase (matching is case-insensitive)"
        )
