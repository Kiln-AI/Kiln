import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    return project


@pytest.fixture
def sample_rag_config_data():
    """Sample data for creating a RagConfig instance."""
    return {
        "name": "Test RAG Config",
        "description": "A test RAG config for testing purposes",
        "tool_name": "test_search_tool",
        "tool_description": "A test search tool for document retrieval",
        "extractor_config_id": "extractor123",
        "chunker_config_id": "chunker456",
        "embedding_config_id": "embedding789",
        "vector_store_config_id": "vector_store123",
    }


def test_rag_config_valid_creation(sample_rag_config_data):
    """Test creating a RagConfig with all required fields."""
    rag_config = RagConfig(**sample_rag_config_data)

    assert rag_config.name == "Test RAG Config"
    assert rag_config.description == "A test RAG config for testing purposes"
    assert rag_config.tool_name == "test_search_tool"
    assert rag_config.tool_description == "A test search tool for document retrieval"
    assert rag_config.extractor_config_id == "extractor123"
    assert rag_config.chunker_config_id == "chunker456"
    assert rag_config.embedding_config_id == "embedding789"
    assert rag_config.vector_store_config_id == "vector_store123"
    assert not rag_config.is_archived  # Default value


def test_rag_config_minimal_creation():
    """Test creating a RagConfig with only required fields."""
    rag_config = RagConfig(
        name="Minimal RAG Config",
        tool_name="minimal_search_tool",
        tool_description="A minimal search tool for testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.name == "Minimal RAG Config"
    assert rag_config.description is None
    assert rag_config.tool_name == "minimal_search_tool"
    assert rag_config.tool_description == "A minimal search tool for testing"
    assert rag_config.extractor_config_id == "extractor123"
    assert rag_config.chunker_config_id == "chunker456"
    assert rag_config.embedding_config_id == "embedding789"
    assert rag_config.vector_store_config_id == "vector_store123"


def test_rag_config_missing_required_fields():
    """Test that missing required fields raise ValidationError."""
    # Test missing name
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
            tool_name="test_tool",
            tool_description="A test tool for missing required fields testing",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "name" for error in errors)

    # Test missing extractor_config_id
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
            name="test_config",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "extractor_config_id" for error in errors)

    # Test missing chunker_config_id
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
            name="Test Config",
            tool_name="test_tool",
            tool_description="A test tool for chunker config ID testing",
            extractor_config_id="extractor123",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "chunker_config_id" for error in errors)

    # Test missing embedding_config_id
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
            name="Test Config",
            tool_name="test_tool",
            tool_description="A test tool for embedding config ID testing",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            vector_store_config_id="vector_store123",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "embedding_config_id" for error in errors)

    # Test missing vector_store_config_id
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
            name="Test Config",
            tool_name="test_tool",
            tool_description="A test tool for vector store config ID testing",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "vector_store_config_id" for error in errors)

    # missing tool_name
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
            name="Test Config",
            tool_description="A test tool for tool name testing",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "tool_name" for error in errors)

    # missing tool_description
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
            name="Test Config",
            tool_name="test_tool",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "tool_description" for error in errors)


def test_rag_config_description_optional():
    """Test that description field is optional and can be None."""
    rag_config = RagConfig(
        name="Test Config",
        description=None,
        tool_name="test_tool",
        tool_description="A test tool for description testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.description is None


def test_rag_config_description_string():
    """Test that description field accepts string values."""
    rag_config = RagConfig(
        name="Test Config",
        description="A detailed description of the RAG config",
        tool_name="test_tool",
        tool_description="A test tool for description string testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.description == "A detailed description of the RAG config"


def test_rag_config_id_generation():
    """Test that RagConfig generates an ID automatically."""
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_tool",
        tool_description="A test tool for ID generation",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.id is not None
    assert isinstance(rag_config.id, str)
    assert len(rag_config.id) == 12  # ID should be 12 digits


def test_rag_config_inheritance():
    """Test that RagConfig inherits from KilnParentedModel."""
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for inheritance testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    # Test that it has the expected base class attributes
    assert hasattr(rag_config, "v")  # schema version
    assert hasattr(rag_config, "id")  # unique identifier
    assert hasattr(rag_config, "path")  # file system path
    assert hasattr(rag_config, "created_at")  # creation timestamp
    assert hasattr(rag_config, "created_by")  # creator user ID
    assert hasattr(rag_config, "parent")  # parent reference


def test_rag_config_model_type():
    """Test that RagConfig has the correct model type."""
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for model type testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.model_type == "rag_config"


def test_rag_config_config_id_types():
    """Test that config IDs can be various string formats."""
    # Test with numeric strings
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for config ID testing",
        extractor_config_id="123",
        chunker_config_id="456",
        embedding_config_id="789",
        vector_store_config_id="999",
    )

    assert rag_config.extractor_config_id == "123"
    assert rag_config.chunker_config_id == "456"
    assert rag_config.embedding_config_id == "789"
    assert rag_config.vector_store_config_id == "999"

    # Test with UUID-like strings
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for UUID-like config ID testing",
        extractor_config_id="extractor-123-456-789",
        chunker_config_id="chunker-abc-def-ghi",
        embedding_config_id="embedding-xyz-uvw-rst",
        vector_store_config_id="vector-store-abc-def-ghi",
    )

    assert rag_config.extractor_config_id == "extractor-123-456-789"
    assert rag_config.chunker_config_id == "chunker-abc-def-ghi"
    assert rag_config.embedding_config_id == "embedding-xyz-uvw-rst"
    assert rag_config.vector_store_config_id == "vector-store-abc-def-ghi"


def test_rag_config_serialization():
    """Test that RagConfig can be serialized and deserialized."""
    original_config = RagConfig(
        name="Test Config",
        description="A test config",
        tool_name="test_search_tool",
        tool_description="A test search tool for serialization testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    # Serialize to dict
    config_dict = original_config.model_dump()

    # Deserialize back to object
    deserialized_config = RagConfig(**config_dict)

    assert deserialized_config.name == original_config.name
    assert deserialized_config.description == original_config.description
    assert deserialized_config.tool_name == original_config.tool_name
    assert deserialized_config.tool_description == original_config.tool_description
    assert (
        deserialized_config.extractor_config_id == original_config.extractor_config_id
    )
    assert deserialized_config.chunker_config_id == original_config.chunker_config_id
    assert (
        deserialized_config.embedding_config_id == original_config.embedding_config_id
    )
    assert (
        deserialized_config.vector_store_config_id
        == original_config.vector_store_config_id
    )


def test_rag_config_default_values():
    """Test that RagConfig has appropriate default values."""
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for default values testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    # Test default values
    assert rag_config.description is None
    assert rag_config.v == 1  # schema version default
    assert rag_config.id is not None  # auto-generated ID
    assert rag_config.path is None  # no path by default
    assert rag_config.parent is None  # no parent by default


def test_project_has_rag_configs(mock_project):
    """Test relationship between project and RagConfig."""
    # create 2 rag configs
    rag_config_1 = RagConfig(
        parent=mock_project,
        name="Test Config 1",
        tool_name="test_search_tool_1",
        tool_description="First test search tool for project relationship testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    rag_config_2 = RagConfig(
        parent=mock_project,
        name="Test Config 2",
        tool_name="test_search_tool_2",
        tool_description="Second test search tool for project relationship testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store456",
    )

    # save the rag configs
    rag_config_1.save_to_file()
    rag_config_2.save_to_file()

    # check that the project has the rag configs
    child_rag_configs = mock_project.rag_configs()
    assert len(child_rag_configs) == 2

    for rag_config in child_rag_configs:
        assert rag_config.id in [rag_config_1.id, rag_config_2.id]


def test_parent_project(mock_project):
    """Test that parent project is returned correctly."""
    rag_config = RagConfig(
        parent=mock_project,
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for parent project testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.parent_project() is mock_project


def test_rag_config_parent_project_none():
    """Test that parent project is None if not set."""
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for parent project none testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.parent_project() is None


def test_rag_config_tags_with_none():
    """Test that tags field can be explicitly set to None."""
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for tags none testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
        tags=None,
    )

    assert rag_config.tags is None


def test_rag_config_tags_with_valid_tags():
    """Test that tags field accepts a valid list of strings."""
    tags = ["python", "ml", "backend", "api"]
    rag_config = RagConfig(
        name="Test Config",
        tool_name="test_search_tool",
        tool_description="A test search tool for valid tags testing",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
        tags=tags,
    )

    assert rag_config.tags == tags
    assert isinstance(rag_config.tags, list)
    assert all(isinstance(tag, str) for tag in rag_config.tags)


@pytest.mark.parametrize(
    "invalid_tags,expected_error",
    [
        ([], "Tags cannot be an empty list"),
        (
            ["python", "with spaces", "ml"],
            "Tags cannot contain spaces. Try underscores.",
        ),
        (["python", "   ", "ml"], "Tags cannot contain spaces. Try underscores."),
        (["python", " leading_space"], "Tags cannot contain spaces. Try underscores."),
        (["trailing_space ", "ml"], "Tags cannot contain spaces. Try underscores."),
        (["", "ml"], "Tags cannot be empty."),
    ],
)
def test_rag_config_tags_invalid(invalid_tags, expected_error):
    """Test that tags field rejects invalid inputs."""
    with pytest.raises(ValueError) as exc_info:
        RagConfig(
            name="Test Config",
            tool_name="test_search_tool",
            tool_description="A test search tool for invalid tags testing",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
            tags=invalid_tags,
        )
    assert expected_error in str(exc_info.value)


def test_rag_config_tool_description_string_values():
    """Test that tool_description accepts various string values."""
    test_cases = [
        "Simple description",
        "A very detailed description of what this tool does and how it should be used by the model.",
        "Description with\nnewlines\nand special chars!@#$%^&*()",
        "Multi-line description\nwith detailed explanation\nof tool capabilities",
        "Description with Unicode: 测试描述 🚀",
    ]

    for tool_description in test_cases:
        rag_config = RagConfig(
            name="Test Config",
            tool_name="test_tool",
            tool_description=tool_description,
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )
        assert rag_config.tool_description == tool_description


def test_rag_config_tool_fields_in_model_dump():
    """Test that tool_name and tool_description are included in model serialization."""
    rag_config = RagConfig(
        name="Test Config",
        tool_name="serialization_test_tool",
        tool_description="A tool for testing serialization of tool fields",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    serialized = rag_config.model_dump()

    assert "tool_name" in serialized
    assert "tool_description" in serialized
    assert serialized["tool_name"] == "serialization_test_tool"
    assert (
        serialized["tool_description"]
        == "A tool for testing serialization of tool fields"
    )


@pytest.mark.parametrize(
    "tool_name,tool_description,expected_error",
    [
        # Empty tool_name
        ("", "Valid description", "Tool name cannot be empty"),
        # Empty tool_description
        ("valid_tool", "", "Tool description cannot be empty"),
        # Whitespace-only tool_name
        ("   ", "Valid description", "Tool name cannot be empty"),
        # Whitespace-only tool_description
        ("valid_tool", "   ", "Tool description cannot be empty"),
        # Tab and newline whitespace
        ("\t\n", "Valid description", "Tool name cannot be empty"),
        ("valid_tool", "\t\n", "Tool description cannot be empty"),
    ],
)
def test_rag_config_tool_fields_validation_edge_cases(
    tool_name, tool_description, expected_error
):
    """Test edge cases for tool_name and tool_description validation."""
    with pytest.raises(ValueError, match=expected_error):
        RagConfig(
            name="Test Config",
            tool_name=tool_name,
            tool_description=tool_description,
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )


@pytest.mark.parametrize(
    "tool_name,expected_error",
    [
        ("Invalid Tool Name", "Tool name must be in snake_case"),
        ("", "Tool name cannot be empty"),
        ("a" * 65, "Tool name must be less than 64 characters long"),
    ],
)
def test_rag_config_tool_name_validation(tool_name, expected_error):
    """Test that tool_name validation works."""
    # Not exhaustive, just an integration test that the validator is called. The validator is tested in utils/test_validation.py.
    with pytest.raises(ValueError) as exc_info:
        RagConfig(
            name="Test Config",
            tool_name=tool_name,
            tool_description="A test search tool for invalid tool name testing",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
            vector_store_config_id="vector_store123",
        )
    assert expected_error in str(exc_info.value)


def test_rag_config_is_archived_field():
    """Test the is_archived field functionality."""
    # Test default value
    rag_config = RagConfig(
        name="Test RAG Config",
        tool_name="test_search_tool",
        tool_description="A test search tool",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )
    assert not rag_config.is_archived

    # Test explicit False
    rag_config = RagConfig(
        name="Test RAG Config",
        tool_name="test_search_tool",
        tool_description="A test search tool",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
        is_archived=False,
    )
    assert not rag_config.is_archived

    # Test explicit True
    rag_config = RagConfig(
        name="Test RAG Config",
        tool_name="test_search_tool",
        tool_description="A test search tool",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
        is_archived=True,
    )
    assert rag_config.is_archived


def test_rag_config_archived_persistence(mock_project, sample_rag_config_data):
    """Test that is_archived field persists when saving and loading."""
    # Create archived config
    rag_config = RagConfig(
        parent=mock_project,
        is_archived=True,
        **sample_rag_config_data,
    )
    rag_config.save_to_file()

    assert rag_config.id

    # Load it back
    loaded_config = RagConfig.from_id_and_parent_path(rag_config.id, mock_project.path)
    assert loaded_config is not None
    assert loaded_config.is_archived

    # Test unarchiving
    loaded_config.is_archived = False
    loaded_config.save_to_file()

    # Load it back again
    reloaded_config = RagConfig.from_id_and_parent_path(
        rag_config.id, mock_project.path
    )
    assert reloaded_config is not None
    assert not reloaded_config.is_archived
