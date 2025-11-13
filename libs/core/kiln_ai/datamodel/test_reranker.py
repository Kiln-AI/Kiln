import uuid

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.reranker import (
    CohereCompatibleProperties,
    RerankerConfig,
    RerankerType,
)


@pytest.fixture
def mock_project(tmp_path):
    project_root = tmp_path / str(uuid.uuid4())
    project_root.mkdir()
    project = Project(
        name="Test Project",
        description="Test description",
        path=project_root / "project.kiln",
    )
    project.save_to_file()
    return project


class TestRerankerConfigValid:
    """Test RerankerConfig with valid inputs."""

    def test_required_fields(self):
        """Test that required fields are set correctly."""
        config = RerankerConfig(
            name="test-reranker",
            top_n=10,
            model_provider_name="cohere",
            model_name="rerank-english-v3.0",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        assert config.name == "test-reranker"
        assert config.top_n == 10
        assert config.model_provider_name == "cohere"
        assert config.model_name == "rerank-english-v3.0"
        assert config.properties == {"type": RerankerType.COHERE_COMPATIBLE}
        assert config.description is None

    def test_with_description(self):
        """Test that description can be set."""
        config = RerankerConfig(
            name="test-reranker",
            description="A test reranker config",
            top_n=5,
            model_provider_name="cohere",
            model_name="rerank-multilingual-v3.0",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        assert config.description == "A test reranker config"

    def test_parent_project_method_no_parent(self):
        """Test parent_project method when no parent is set."""
        config = RerankerConfig(
            name="test-reranker",
            top_n=10,
            model_provider_name="cohere",
            model_name="rerank-english-v3.0",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        assert config.parent_project() is None


class TestRerankerConfigInvalidInputs:
    """Test RerankerConfig with invalid inputs."""

    def test_missing_name(self):
        """Test that missing name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RerankerConfig(
                top_n=10,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("name",) for error in errors)

    def test_empty_name(self):
        """Test that empty name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RerankerConfig(
                name="",
                top_n=10,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )
        errors = exc_info.value.errors()
        assert any("Name is too short" in str(error["msg"]) for error in errors)

    def test_missing_top_n(self):
        """Test that missing top_n raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RerankerConfig(
                name="test-reranker",
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("top_n",) for error in errors)

    def test_top_n_not_integer(self):
        """Test that non-integer top_n raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n="not-an-int",
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )

    def test_missing_model_provider_name(self):
        """Test that missing model_provider_name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("model_provider_name",) for error in errors)

    def test_model_provider_name_not_string(self):
        """Test that non-string model_provider_name raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_provider_name=123,
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )

    def test_missing_model_name(self):
        """Test that missing model_name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_provider_name="cohere",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("model_name",) for error in errors)

    def test_model_name_not_string(self):
        """Test that non-string model_name raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_provider_name="cohere",
                model_name=456,
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )

    def test_missing_properties(self):
        """Test that missing properties raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
            )
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("properties",) for error in errors)

    def test_properties_wrong_type(self):
        """Test that properties with wrong type raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties="not-a-dict",
            )

    def test_properties_missing_type_field(self):
        """Test that properties missing type field raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={},
            )

    def test_properties_invalid_type_value(self):
        """Test that properties with invalid type value raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n=10,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={"type": "invalid_type"},
            )

    def test_properties_valid_cohere_compatible(self):
        """Test that properties with valid COHERE_COMPATIBLE type works."""
        config = RerankerConfig(
            name="test-reranker",
            top_n=10,
            model_provider_name="cohere",
            model_name="rerank-english-v3.0",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        assert config.properties["type"] == RerankerType.COHERE_COMPATIBLE

    def test_multiple_invalid_fields(self):
        """Test that multiple invalid fields produce multiple errors."""
        with pytest.raises(ValidationError) as exc_info:
            RerankerConfig(
                name="",
                top_n="not-an-int",
                model_provider_name=123,
                model_name=456,
                properties="not-a-dict",
            )
        errors = exc_info.value.errors()
        assert len(errors) >= 5


class TestRerankerConfigEdgeCases:
    """Test RerankerConfig edge cases."""

    def test_top_n_zero(self):
        """Test that top_n of 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n=0,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )

    def test_top_n_negative(self):
        """Test that negative top_n raises ValidationError."""
        with pytest.raises(ValidationError):
            RerankerConfig(
                name="test-reranker",
                top_n=-1,
                model_provider_name="cohere",
                model_name="rerank-english-v3.0",
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )

    def test_description_empty_string(self):
        """Test that empty description string is valid."""
        config = RerankerConfig(
            name="test-reranker",
            description="",
            top_n=10,
            model_provider_name="cohere",
            model_name="rerank-english-v3.0",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        assert config.description == ""

    def test_valid_name_with_underscores_and_hyphens(self):
        """Test that names with underscores and hyphens are valid."""
        config = RerankerConfig(
            name="test_reranker-config",
            top_n=10,
            model_provider_name="cohere",
            model_name="rerank-english-v3.0",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        assert config.name == "test_reranker-config"

    def test_valid_name_with_numbers(self):
        """Test that names with numbers are valid."""
        config = RerankerConfig(
            name="reranker-123-test",
            top_n=10,
            model_provider_name="cohere",
            model_name="rerank-english-v3.0",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        assert config.name == "reranker-123-test"


class TestRerankerType:
    """Test RerankerType enum."""

    def test_cohere_compatible_value(self):
        """Test that COHERE_COMPATIBLE has correct value."""
        assert RerankerType.COHERE_COMPATIBLE == "cohere_compatible"

    def test_reranker_type_enum_values(self):
        """Test all RerankerType enum values."""
        values = [member.value for member in RerankerType]
        assert RerankerType.COHERE_COMPATIBLE in values


class TestCohereCompatibleProperties:
    """Test CohereCompatibleProperties TypedDict."""

    def test_valid_properties(self):
        """Test that valid properties dictionary works."""
        props = CohereCompatibleProperties(type=RerankerType.COHERE_COMPATIBLE)
        assert props["type"] == RerankerType.COHERE_COMPATIBLE
