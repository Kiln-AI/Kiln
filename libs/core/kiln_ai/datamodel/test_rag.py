import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RAGPipeline


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    return project


@pytest.fixture
def sample_rag_pipeline_data():
    """Sample data for creating a RAGPipeline instance."""
    return {
        "name": "Test RAG Pipeline",
        "description": "A test RAG pipeline for testing purposes",
        "extractor_config_id": "extractor123",
        "chunker_config_id": "chunker456",
        "embedding_config_id": "embedding789",
    }


def test_rag_pipeline_valid_creation(sample_rag_pipeline_data):
    """Test creating a RAGPipeline with all required fields."""
    rag_pipeline = RAGPipeline(**sample_rag_pipeline_data)

    assert rag_pipeline.name == "Test RAG Pipeline"
    assert rag_pipeline.description == "A test RAG pipeline for testing purposes"
    assert rag_pipeline.extractor_config_id == "extractor123"
    assert rag_pipeline.chunker_config_id == "chunker456"
    assert rag_pipeline.embedding_config_id == "embedding789"


def test_rag_pipeline_minimal_creation():
    """Test creating a RAGPipeline with only required fields."""
    rag_pipeline = RAGPipeline(
        name="Minimal RAG Pipeline",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    assert rag_pipeline.name == "Minimal RAG Pipeline"
    assert rag_pipeline.description is None
    assert rag_pipeline.extractor_config_id == "extractor123"
    assert rag_pipeline.chunker_config_id == "chunker456"
    assert rag_pipeline.embedding_config_id == "embedding789"


def test_rag_pipeline_missing_required_fields():
    """Test that missing required fields raise ValidationError."""
    # Test missing name
    with pytest.raises(ValidationError) as exc_info:
        RAGPipeline(
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "name" for error in errors)

    # Test missing extractor_config_id
    with pytest.raises(ValidationError) as exc_info:
        RAGPipeline(
            name="Test Pipeline",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "extractor_config_id" for error in errors)

    # Test missing chunker_config_id
    with pytest.raises(ValidationError) as exc_info:
        RAGPipeline(
            name="Test Pipeline",
            extractor_config_id="extractor123",
            embedding_config_id="embedding789",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "chunker_config_id" for error in errors)

    # Test missing embedding_config_id
    with pytest.raises(ValidationError) as exc_info:
        RAGPipeline(
            name="Test Pipeline",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
        )
    errors = exc_info.value.errors()
    assert any(error["loc"][0] == "embedding_config_id" for error in errors)


def test_rag_pipeline_name_validation():
    """Test name field validation according to NAME_FIELD constraints."""
    # Valid names
    RAGPipeline(
        name="Valid Name",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    RAGPipeline(
        name="Valid_Name-With_123",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    RAGPipeline(
        name="a",  # Minimum length
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    RAGPipeline(
        name="a" * 120,  # Maximum length
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    # Invalid names
    with pytest.raises(ValidationError):
        RAGPipeline(
            name="",  # Empty string
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )

    with pytest.raises(ValidationError):
        RAGPipeline(
            name="a" * 121,  # Too long
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )

    with pytest.raises(ValidationError):
        RAGPipeline(
            name="Invalid!Name",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )

    with pytest.raises(ValidationError):
        RAGPipeline(
            name="Invalid.Name",
            extractor_config_id="extractor123",
            chunker_config_id="chunker456",
            embedding_config_id="embedding789",
        )


def test_rag_pipeline_description_optional():
    """Test that description field is optional and can be None."""
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        description=None,
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    assert rag_pipeline.description is None


def test_rag_pipeline_description_string():
    """Test that description field accepts string values."""
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        description="A detailed description of the RAG pipeline",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    assert rag_pipeline.description == "A detailed description of the RAG pipeline"


def test_rag_pipeline_id_generation():
    """Test that RAGPipeline generates an ID automatically."""
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    assert rag_pipeline.id is not None
    assert isinstance(rag_pipeline.id, str)
    assert len(rag_pipeline.id) == 12  # ID should be 12 digits


def test_rag_pipeline_inheritance():
    """Test that RAGPipeline inherits from KilnParentedModel."""
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    # Test that it has the expected base class attributes
    assert hasattr(rag_pipeline, "v")  # schema version
    assert hasattr(rag_pipeline, "id")  # unique identifier
    assert hasattr(rag_pipeline, "path")  # file system path
    assert hasattr(rag_pipeline, "created_at")  # creation timestamp
    assert hasattr(rag_pipeline, "created_by")  # creator user ID
    assert hasattr(rag_pipeline, "parent")  # parent reference


def test_rag_pipeline_model_type():
    """Test that RAGPipeline has the correct model type."""
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    assert rag_pipeline.model_type == "r_a_g_pipeline"


def test_rag_pipeline_config_id_types():
    """Test that config IDs can be various string formats."""
    # Test with numeric strings
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        extractor_config_id="123",
        chunker_config_id="456",
        embedding_config_id="789",
    )

    assert rag_pipeline.extractor_config_id == "123"
    assert rag_pipeline.chunker_config_id == "456"
    assert rag_pipeline.embedding_config_id == "789"

    # Test with UUID-like strings
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        extractor_config_id="extractor-123-456-789",
        chunker_config_id="chunker-abc-def-ghi",
        embedding_config_id="embedding-xyz-uvw-rst",
    )

    assert rag_pipeline.extractor_config_id == "extractor-123-456-789"
    assert rag_pipeline.chunker_config_id == "chunker-abc-def-ghi"
    assert rag_pipeline.embedding_config_id == "embedding-xyz-uvw-rst"


def test_rag_pipeline_serialization():
    """Test that RAGPipeline can be serialized and deserialized."""
    original_pipeline = RAGPipeline(
        name="Test Pipeline",
        description="A test pipeline",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    # Serialize to dict
    pipeline_dict = original_pipeline.model_dump()

    # Deserialize back to object
    deserialized_pipeline = RAGPipeline(**pipeline_dict)

    assert deserialized_pipeline.name == original_pipeline.name
    assert deserialized_pipeline.description == original_pipeline.description
    assert (
        deserialized_pipeline.extractor_config_id
        == original_pipeline.extractor_config_id
    )
    assert (
        deserialized_pipeline.chunker_config_id == original_pipeline.chunker_config_id
    )
    assert (
        deserialized_pipeline.embedding_config_id
        == original_pipeline.embedding_config_id
    )


def test_rag_pipeline_default_values():
    """Test that RAGPipeline has appropriate default values."""
    rag_pipeline = RAGPipeline(
        name="Test Pipeline",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    # Test default values
    assert rag_pipeline.description is None
    assert rag_pipeline.v == 1  # schema version default
    assert rag_pipeline.id is not None  # auto-generated ID
    assert rag_pipeline.path is None  # no path by default
    assert rag_pipeline.parent is None  # no parent by default


def test_project_has_rag_pipelines(mock_project):
    """Test relationship between project and RAGPipeline."""
    # create 2 rag pipelines
    rag_pipeline_1 = RAGPipeline(
        parent=mock_project,
        name="Test Pipeline 1",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    rag_pipeline_2 = RAGPipeline(
        parent=mock_project,
        name="Test Pipeline 2",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
    )

    # save the rag pipelines
    rag_pipeline_1.save_to_file()
    rag_pipeline_2.save_to_file()

    # check that the project has the rag pipelines
    child_rag_pipelines = mock_project.rag_pipelines()
    assert len(child_rag_pipelines) == 2

    for rag_pipeline in child_rag_pipelines:
        assert rag_pipeline.id in [rag_pipeline_1.id, rag_pipeline_2.id]
