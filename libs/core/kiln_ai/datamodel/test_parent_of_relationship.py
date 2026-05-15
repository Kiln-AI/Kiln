from pathlib import Path

import pytest

from kiln_ai.datamodel.basemodel import (
    FilenameString,
    KilnParentedModel,
    KilnParentModel,
    ParentOfRelationship,
)


class _TestChild(KilnParentedModel):
    name: FilenameString


class _TestParentLegacy(KilnParentModel, parent_of={"children": _TestChild}):
    name: FilenameString


class _TestChildRel(KilnParentedModel):
    name: FilenameString


class _TestParentRelationship(
    KilnParentModel,
    parent_of={
        "_kids": ParentOfRelationship(model=_TestChildRel, filesystem_name="kids"),
    },
):
    name: FilenameString


@pytest.fixture
def legacy_parent(tmp_path: Path) -> _TestParentLegacy:
    parent_path = tmp_path / "legacy" / "test_parent_legacy.kiln"
    parent_path.parent.mkdir(parents=True, exist_ok=True)
    parent = _TestParentLegacy(name="legacy_parent", path=parent_path)
    parent.save_to_file()
    return parent


@pytest.fixture
def relationship_parent(tmp_path: Path) -> _TestParentRelationship:
    parent_path = tmp_path / "rel" / "test_parent_relationship.kiln"
    parent_path.parent.mkdir(parents=True, exist_ok=True)
    parent = _TestParentRelationship(name="rel_parent", path=parent_path)
    parent.save_to_file()
    return parent


def test_legacy_form_python_attr_matches_filesystem(legacy_parent: _TestParentLegacy):
    # The Python attr name (key) is used for both attribute access and disk folder.
    assert callable(getattr(_TestParentLegacy, "children"))
    assert _TestChild.relationship_name() == "children"

    child = _TestChild(name="kid1", parent=legacy_parent)
    child.save_to_file()

    # Disk folder should be "children/"
    assert legacy_parent.path is not None
    parent_folder = legacy_parent.path.parent
    assert (parent_folder / "children").is_dir()

    # Round-trip via the auto-generated relationship method.
    loaded_children = legacy_parent.children()
    assert len(loaded_children) == 1
    assert loaded_children[0].name == "kid1"


def test_relationship_form_decouples_python_and_filesystem(
    relationship_parent: _TestParentRelationship,
):
    # Python attribute uses the dict key.
    assert callable(getattr(_TestParentRelationship, "_kids"))
    # The plain key ("_kids") must NOT be an auto-generated public method on the class.
    assert not hasattr(_TestParentRelationship, "kids")

    child = _TestChildRel(name="kid_rel", parent=relationship_parent)
    child.save_to_file()

    assert relationship_parent.path is not None
    parent_folder = relationship_parent.path.parent

    # On-disk folder must be "kids/" (filesystem_name), not "_kids/".
    assert (parent_folder / "kids").is_dir()
    assert not (parent_folder / "_kids").exists()

    # Confirm we can round-trip via the auto-generated method named with the key.
    loaded = relationship_parent._kids()
    assert len(loaded) == 1
    assert loaded[0].name == "kid_rel"


def test_relationship_name_returns_filesystem_name():
    # The child's relationship_name() must return the filesystem name, not the python attr.
    assert _TestChildRel.relationship_name() == "kids"


def test_relationship_form_child_path_uses_filesystem_name(
    relationship_parent: _TestParentRelationship,
):
    # build_path on the child should produce a path containing "kids", not "_kids".
    child = _TestChildRel(name="path_check", parent=relationship_parent)
    built_path = child.build_path()
    assert built_path is not None
    assert "kids" in built_path.parts
    assert "_kids" not in built_path.parts


def test_parent_of_relationship_is_frozen():
    rel = ParentOfRelationship(model=_TestChildRel, filesystem_name="kids")
    with pytest.raises(Exception):
        rel.filesystem_name = "other"  # type: ignore[misc]


def test_validate_nested_rejects_filesystem_name_used_as_payload_key(tmp_path: Path):
    """Passing the on-disk folder name as a nested payload key must fail loudly.

    Previously this would silently drop the nested payload (since the key
    wasn't in ``_parent_of``), making it easy to miss when migrating callers.
    """
    parent_path = tmp_path / "fail_loud" / "test_parent_relationship.kiln"
    parent_path.parent.mkdir(parents=True, exist_ok=True)

    bad_payload = {
        "name": "rel_parent_bad",
        "path": str(parent_path),
        # "kids" is the filesystem_name; callers must use "_kids" (the python
        # attr name) for nested payloads.
        "kids": [{"name": "kid_via_wrong_key"}],
    }

    with pytest.raises(ValueError, match=r"Use the Python attribute name '_kids'"):
        _TestParentRelationship.validate_and_save_with_subrelations(bad_payload)

    # And the correct Python attribute name still works.
    good_payload = {
        "name": "rel_parent_good",
        "path": str(parent_path),
        "_kids": [{"name": "kid_via_correct_key"}],
    }
    _TestParentRelationship.validate_and_save_with_subrelations(good_payload)
