import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.document_skill import DocumentSkill
from kiln_ai.datamodel.project import Project


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def sample_doc_skill_data():
    return {
        "name": "Test Doc Skill",
        "skill_name": "my-doc-skill",
        "skill_content_header": "This skill provides reference documents.",
        "extractor_config_id": "extractor123",
        "chunker_config_id": "chunker456",
    }


def test_valid_creation_all_fields():
    ds = DocumentSkill(
        name="Full Doc Skill",
        description="A detailed description",
        skill_name="full-doc-skill",
        skill_content_header="Documents about APIs.",
        extractor_config_id="ext1",
        chunker_config_id="chunk1",
        document_tags=["api", "docs"],
        strip_file_extensions=False,
    )
    assert ds.name == "Full Doc Skill"
    assert ds.description == "A detailed description"
    assert ds.skill_name == "full-doc-skill"
    assert ds.skill_content_header == "Documents about APIs."
    assert ds.extractor_config_id == "ext1"
    assert ds.chunker_config_id == "chunk1"
    assert ds.document_tags == ["api", "docs"]
    assert ds.strip_file_extensions is False
    assert ds.skill_id is None
    assert ds.is_archived is False


def test_minimal_creation(sample_doc_skill_data):
    ds = DocumentSkill(**sample_doc_skill_data)
    assert ds.name == "Test Doc Skill"
    assert ds.description is None
    assert ds.document_tags is None
    assert ds.skill_id is None
    assert ds.strip_file_extensions is True
    assert ds.is_archived is False


def test_defaults(sample_doc_skill_data):
    ds = DocumentSkill(**sample_doc_skill_data)
    assert ds.skill_id is None
    assert ds.strip_file_extensions is True
    assert ds.is_archived is False
    assert ds.id is not None


@pytest.mark.parametrize(
    "invalid_tags,expected_error",
    [
        ([], "Document tags cannot be an empty list"),
        (["valid", ""], "Document tags cannot be empty"),
        (["with spaces"], "Document tags cannot contain spaces. Try underscores."),
        (["leading space"], "Document tags cannot contain spaces. Try underscores."),
    ],
)
def test_tag_validation_invalid(sample_doc_skill_data, invalid_tags, expected_error):
    with pytest.raises(ValueError, match=expected_error):
        DocumentSkill(**sample_doc_skill_data, document_tags=invalid_tags)


@pytest.mark.parametrize(
    "valid_tags",
    [
        None,
        ["single"],
        ["tag_one", "tag_two"],
        ["with-hyphens", "with_underscores"],
    ],
)
def test_tag_validation_valid(sample_doc_skill_data, valid_tags):
    ds = DocumentSkill(**sample_doc_skill_data, document_tags=valid_tags)
    assert ds.document_tags == valid_tags


@pytest.mark.parametrize(
    "skill_content_header",
    [
        "",
        "   ",
        "\t\n",
    ],
)
def test_skill_content_header_validation(sample_doc_skill_data, skill_content_header):
    data = {**sample_doc_skill_data, "skill_content_header": skill_content_header}
    with pytest.raises((ValidationError, ValueError)):
        DocumentSkill(**data)


@pytest.mark.parametrize(
    "skill_name,expected_error",
    [
        ("Invalid Name", "Skill name may only contain lowercase letters"),
        ("a" * 65, "Skill name must be 64 characters or fewer"),
    ],
)
def test_skill_name_validation(sample_doc_skill_data, skill_name, expected_error):
    data = {**sample_doc_skill_data, "skill_name": skill_name}
    with pytest.raises(ValueError, match=expected_error):
        DocumentSkill(**data)


def test_save_load_roundtrip(mock_project, sample_doc_skill_data):
    ds = DocumentSkill(
        parent=mock_project,
        document_tags=["api"],
        **sample_doc_skill_data,
    )
    ds.save_to_file()

    loaded = DocumentSkill.from_id_and_parent_path(ds.id, mock_project.path)
    assert loaded is not None
    assert loaded.name == ds.name
    assert loaded.skill_name == ds.skill_name
    assert loaded.skill_content_header == ds.skill_content_header
    assert loaded.extractor_config_id == ds.extractor_config_id
    assert loaded.chunker_config_id == ds.chunker_config_id
    assert loaded.document_tags == ["api"]
    assert loaded.strip_file_extensions is True
    assert loaded.skill_id is None


def test_parent_project(mock_project, sample_doc_skill_data):
    ds = DocumentSkill(parent=mock_project, **sample_doc_skill_data)
    assert ds.parent_project() is mock_project


def test_parent_project_none(sample_doc_skill_data):
    ds = DocumentSkill(**sample_doc_skill_data)
    assert ds.parent_project() is None


def test_listing_via_project(mock_project, sample_doc_skill_data):
    ds1 = DocumentSkill(parent=mock_project, **sample_doc_skill_data)
    ds1.save_to_file()

    ds2 = DocumentSkill(
        parent=mock_project,
        name="Second Doc Skill",
        skill_name="second-doc-skill",
        skill_content_header="More documents.",
        extractor_config_id="ext2",
        chunker_config_id="chunk2",
    )
    ds2.save_to_file()

    children = mock_project.document_skills()
    assert len(children) == 2
    child_ids = {c.id for c in children}
    assert ds1.id in child_ids
    assert ds2.id in child_ids


def test_model_type(sample_doc_skill_data):
    ds = DocumentSkill(**sample_doc_skill_data)
    assert ds.model_type == "document_skill"


def test_archived_persistence(mock_project, sample_doc_skill_data):
    ds = DocumentSkill(parent=mock_project, is_archived=True, **sample_doc_skill_data)
    ds.save_to_file()

    loaded = DocumentSkill.from_id_and_parent_path(ds.id, mock_project.path)
    assert loaded is not None
    assert loaded.is_archived is True
