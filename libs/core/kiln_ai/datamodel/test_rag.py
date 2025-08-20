import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    return project


@pytest.fixture
def sample_rag_config_data():
    """Sample data for creating a RagConfig instance."""
    return {
        "name": "Test RAG Config",
        "description": "A test RAG config for testing purposes",
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
    assert rag_config.extractor_config_id == "extractor123"
    assert rag_config.chunker_config_id == "chunker456"
    assert rag_config.embedding_config_id == "embedding789"
    assert rag_config.vector_store_config_id == "vector_store123"


def test_rag_config_minimal_creation():
    """Test creating a RagConfig with only required fields."""
    rag_config = RagConfig(
        name="Minimal RAG Config",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    assert rag_config.name == "Minimal RAG Config"
    assert rag_config.description is None
    assert rag_config.extractor_config_id == "extractor123"
    assert rag_config.chunker_config_id == "chunker456"
    assert rag_config.embedding_config_id == "embedding789"
    assert rag_config.vector_store_config_id == "vector_store123"


def test_rag_config_missing_required_fields():
    """Test that missing required fields raise ValidationError."""
    # Test missing name
    with pytest.raises(ValidationError) as exc_info:
        RagConfig(
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
            name="Test Config",
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
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "vector_store_config_id" for error in errors)


def test_rag_config_description_optional():
    """Test that description field is optional and can be None."""
    rag_config = RagConfig(
        name="Test Config",
        description=None,
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
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    rag_config_2 = RagConfig(
        parent=mock_project,
        name="Test Config 2",
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
