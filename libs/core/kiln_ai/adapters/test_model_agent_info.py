from typing import Mapping

import pytest

from kiln_ai.adapters.model_agent_info import (
    MAX_NOTE_CHARS,
    MAX_TAGS_PER_ENTRY,
    MODEL_TAGS,
    PROVIDER_ENTRY_TAGS,
    PROVIDER_LIST_TAGS,
    TAG_PATTERN,
)


def assert_valid_tags(tags: list[str], allowed: Mapping[str, str]) -> None:
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


ALL_TAG_MAPS = {
    "MODEL_TAGS": MODEL_TAGS,
    "PROVIDER_ENTRY_TAGS": PROVIDER_ENTRY_TAGS,
    "PROVIDER_LIST_TAGS": PROVIDER_LIST_TAGS,
}


@pytest.mark.parametrize(
    "map_name, tag, meaning",
    [
        pytest.param(map_name, tag, meaning, id=f"{map_name}-{tag}")
        for map_name, tag_map in ALL_TAG_MAPS.items()
        for tag, meaning in tag_map.items()
    ],
)
def test_tag_map_entries_are_well_formed(map_name, tag, meaning):
    assert TAG_PATTERN.match(tag), f"{map_name} key {tag!r} has a bad format"
    assert isinstance(meaning, str) and meaning.strip()


def test_no_tag_in_both_model_and_provider_entry_maps():
    assert not set(MODEL_TAGS) & set(PROVIDER_ENTRY_TAGS)


def test_starting_tags():
    # Adding a tag means updating this test too, so the new tag gets reviewed.
    assert set(MODEL_TAGS) == {
        "best_value",
        "strong_agentic",
        "strong_coding",
        "strong_writing",
        "verbose",
    }
    assert set(PROVIDER_ENTRY_TAGS) == {"fast", "very_fast"}
    assert dict(PROVIDER_LIST_TAGS) == {}


@pytest.mark.parametrize(
    "tags",
    [
        [],
        ["best_value"],
        ["best_value", "strong_coding", "verbose"],
    ],
)
def test_assert_valid_tags_accepts_valid_tags(tags):
    assert_valid_tags(tags, MODEL_TAGS)


@pytest.mark.parametrize(
    "tags, allowed, message",
    [
        (["Best_Value"], {"Best_Value": "x"}, "does not match"),
        (["best-value"], {"best-value": "x"}, "does not match"),
        (["a" * 41], {"a" * 41: "x"}, "does not match"),
        (["fast"], MODEL_TAGS, "not in the allowed tags"),
        (["verbose", "verbose"], MODEL_TAGS, "Duplicate tags"),
        (
            [f"tag_{i}" for i in range(MAX_TAGS_PER_ENTRY + 1)],
            {f"tag_{i}": "x" for i in range(MAX_TAGS_PER_ENTRY + 1)},
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
