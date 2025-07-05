import tempfile
import uuid
from pathlib import Path

import pytest

from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
from kiln_ai.datamodel.project import Project


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


@pytest.fixture
def mock_chunked_document(tmp_path):
    # Create a temporary file for the attachment
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path_file = Path(tmp_dir) / f"{uuid.uuid4()}.txt"
        tmp_path_file.write_text("test content")

        attachment = KilnAttachmentModel.from_file(tmp_path_file)
        chunks = [Chunk(content=attachment) for _ in range(3)]

        doc = ChunkedDocument(
            chunks=chunks,
            chunker_config_id="fake-chunker-id",
            path=Path(tmp_dir) / "chunked_document.kiln",
        )
        doc.save_to_file()

        return doc


class TestEmbeddingConfig:
    """Test the EmbeddingConfig class."""

    def test_required_fields(self):
        """Test that required fields are set correctly."""
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
        )
        assert config.name == "test-embedding"
        assert config.model_provider_name == "openai"
        assert config.model_name == "openai_text_embedding_3_small"
        assert config.properties == {"dimensions": 1536}

    def test_optional_description(self):
        """Test that description is optional."""
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
        )
        assert config.description is None

        config_with_desc = EmbeddingConfig(
            name="test-embedding",
            description="A test embedding config",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
        )
        assert config_with_desc.description == "A test embedding config"

    def test_name_validation(self):
        """Test name field validation."""
        # Test valid name
        config = EmbeddingConfig(
            name="valid-name_123",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
        )
        assert config.name == "valid-name_123"

        # Test invalid name (contains special characters)
        with pytest.raises(ValueError):
            EmbeddingConfig(
                name="invalid@name",
                model_provider_name="openai",
                model_name="openai_text_embedding_3_small",
                properties={"dimensions": 1536},
            )

        # Test empty name
        with pytest.raises(ValueError):
            EmbeddingConfig(
                name="",
                model_provider_name="openai",
                model_name="openai_text_embedding_3_small",
                properties={"dimensions": 1536},
            )

    def test_properties_validation(self):
        """Test properties field validation."""
        # Test with valid properties
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={
                "dimensions": 1536,
            },
        )
        assert config.properties == {
            "dimensions": 1536,
        }

        # Test with empty properties
        config_empty = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={},
        )
        assert config_empty.properties == {}

    def test_parent_project_method_no_parent(self):
        """Test parent_project method when no parent is set."""
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
        )
        assert config.parent_project() is None

    def test_parent_project_method_with_project_parent(self, mock_project):
        """Test parent_project method when parent is a Project."""
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
            parent=mock_project,
        )
        assert config.parent_project() == mock_project

    def test_model_provider_name_validation(self, mock_project):
        """Test model_provider_name field validation."""
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={},
            parent=mock_project,
        )
        assert config.model_provider_name == "openai"

        with pytest.raises(ValueError):
            EmbeddingConfig(
                name="test-embedding",
                model_provider_name="invalid-provider",
                model_name="openai_text_embedding_3_small",
                parent=mock_project,
                properties={},
            )

    def test_custom_dimensions_validation(self):
        """Test that custom dimensions are properly validated."""

        # this model supports custom dimensions
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
        )
        assert config.properties == {"dimensions": 1536}

        # this model does not support custom dimensions
        with pytest.raises(
            ValueError,
            match="The model gemini_text_embedding_004 does not support custom dimensions",
        ):
            EmbeddingConfig(
                name="test-embedding",
                model_provider_name="gemini_api",
                model_name="gemini_text_embedding_004",
                properties={"dimensions": 512},
            )

        # dimensions is negative
        with pytest.raises(ValueError, match="Dimensions must be a positive integer"):
            EmbeddingConfig(
                name="test-embedding",
                model_provider_name="openai",
                model_name="openai_text_embedding_3_small",
                properties={"dimensions": -1},
            )

        # dimensions is not an integer
        with pytest.raises(ValueError, match="Dimensions must be a positive integer"):
            EmbeddingConfig(
                name="test-embedding",
                model_provider_name="openai",
                model_name="openai_text_embedding_3_small",
                properties={"dimensions": 1.5},
            )

        # dimensions is not a positive integer
        with pytest.raises(ValueError, match="Dimensions must be a positive integer"):
            EmbeddingConfig(
                name="test-embedding",
                model_provider_name="openai",
                model_name="openai_text_embedding_3_small",
                properties={"dimensions": "512"},
            )

    def test_dimensions_optional(self):
        """Test that dimensions is optional and should be ignored if not provided."""
        config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={},
        )
        assert config.properties == {}


class TestEmbedding:
    """Test the Embedding class."""

    def test_required_fields(self):
        """Test that required fields are properly validated."""
        vector = [0.1, 0.2, 0.3, 0.4, 0.5]
        embedding = Embedding(vector=vector)
        assert embedding.vector == vector

    def test_vector_validation(self):
        """Test that vector field is properly validated."""
        # Test with valid vector
        vector = [0.1, 0.2, 0.3]
        embedding = Embedding(vector=vector)
        assert embedding.vector == vector

        # Test with empty vector
        empty_vector = []
        embedding_empty = Embedding(vector=empty_vector)
        assert embedding_empty.vector == empty_vector

        # Test with large vector
        large_vector = [0.1] * 1536
        embedding_large = Embedding(vector=large_vector)
        assert len(embedding_large.vector) == 1536

    def test_vector_types(self):
        """Test that vector accepts different numeric types."""
        # Test with integers
        int_vector = [1, 2, 3, 4, 5]
        embedding_int = Embedding(vector=int_vector)
        assert embedding_int.vector == int_vector

        # Test with floats
        float_vector = [1.1, 2.2, 3.3, 4.4, 5.5]
        embedding_float = Embedding(vector=float_vector)
        assert embedding_float.vector == float_vector

        # Test with mixed types
        mixed_vector = [1, 2.5, 3, 4.7, 5]
        embedding_mixed = Embedding(vector=mixed_vector)
        assert embedding_mixed.vector == mixed_vector


class TestChunkEmbeddings:
    """Test the ChunkEmbeddings class."""

    def test_required_fields(self):
        """Test that required fields are properly validated."""
        embedding_config_id = "test-config-id"
        embeddings = [
            Embedding(vector=[0.1, 0.2, 0.3]),
            Embedding(vector=[0.4, 0.5, 0.6]),
        ]

        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id=embedding_config_id,
            embeddings=embeddings,
        )
        assert chunk_embeddings.embedding_config_id == embedding_config_id
        assert chunk_embeddings.embeddings == embeddings

    def test_embeddings_validation(self):
        """Test that embeddings field validation works correctly."""
        embedding_config_id = "test-config-id"

        # Test with valid list of embeddings
        embeddings = [Embedding(vector=[0.1, 0.2, 0.3])]
        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id=embedding_config_id,
            embeddings=embeddings,
        )
        assert chunk_embeddings.embeddings == embeddings

        # Test with empty embeddings list
        empty_embeddings = []
        chunk_embeddings_empty = ChunkEmbeddings(
            embedding_config_id=embedding_config_id,
            embeddings=empty_embeddings,
        )
        assert chunk_embeddings_empty.embeddings == empty_embeddings

        # Test with multiple embeddings
        multiple_embeddings = [
            Embedding(vector=[0.1, 0.2, 0.3]),
            Embedding(vector=[0.4, 0.5, 0.6]),
            Embedding(vector=[0.7, 0.8, 0.9]),
        ]
        chunk_embeddings_multiple = ChunkEmbeddings(
            embedding_config_id=embedding_config_id,
            embeddings=multiple_embeddings,
        )
        assert chunk_embeddings_multiple.embeddings == multiple_embeddings
        assert len(chunk_embeddings_multiple.embeddings) == 3

    def test_embedding_config_id_validation(self):
        """Test embedding_config_id field validation."""
        embeddings = [Embedding(vector=[0.1, 0.2, 0.3])]

        # Test with valid ID
        valid_id = "test-config-id-123"
        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id=valid_id,
            embeddings=embeddings,
        )
        assert chunk_embeddings.embedding_config_id == valid_id

        # Test with numeric string ID
        numeric_id = "12345"
        chunk_embeddings_numeric = ChunkEmbeddings(
            embedding_config_id=numeric_id,
            embeddings=embeddings,
        )
        assert chunk_embeddings_numeric.embedding_config_id == numeric_id

    def test_parent_chunked_document_method_no_parent(self):
        """Test parent_chunked_document method when no parent is set."""
        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id="test-config-id",
            embeddings=[Embedding(vector=[0.1, 0.2, 0.3])],
        )
        assert chunk_embeddings.parent_chunked_document() is None

    def test_parent_chunked_document_method_with_chunked_document_parent(
        self, mock_chunked_document
    ):
        """Test parent_chunked_document method when parent is a ChunkedDocument."""
        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id="test-config-id",
            embeddings=[Embedding(vector=[0.1, 0.2, 0.3])],
            parent=mock_chunked_document,
        )
        assert chunk_embeddings.parent_chunked_document() == mock_chunked_document

    def test_embeddings_correspond_to_chunks(self, mock_chunked_document):
        """Test that embeddings correspond to chunks in the parent chunked document."""
        # Create embeddings that match the number of chunks in the parent
        num_chunks = len(mock_chunked_document.chunks)
        embeddings = [Embedding(vector=[0.1, 0.2, 0.3]) for _ in range(num_chunks)]

        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id="test-config-id",
            embeddings=embeddings,
            parent=mock_chunked_document,
        )
        assert len(chunk_embeddings.embeddings) == num_chunks

    def test_embeddings_with_different_vector_sizes(self):
        """Test embeddings with different vector sizes."""
        embedding_config_id = "test-config-id"
        embeddings = [
            Embedding(vector=[0.1, 0.2, 0.3]),  # 3 dimensions
            Embedding(vector=[0.4, 0.5, 0.6, 0.7]),  # 4 dimensions
            Embedding(vector=[0.8, 0.9]),  # 2 dimensions
        ]

        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id=embedding_config_id,
            embeddings=embeddings,
        )
        assert len(chunk_embeddings.embeddings) == 3
        assert len(chunk_embeddings.embeddings[0].vector) == 3
        assert len(chunk_embeddings.embeddings[1].vector) == 4
        assert len(chunk_embeddings.embeddings[2].vector) == 2


class TestEmbeddingIntegration:
    """Integration tests for embedding models."""

    def test_embedding_config_with_project_parent(self, mock_project):
        """Test EmbeddingConfig with Project parent."""
        config = EmbeddingConfig(
            name="test-embedding",
            description="Test embedding configuration",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
            parent=mock_project,
        )
        assert config.parent_project() == mock_project
        assert config.name == "test-embedding"
        assert config.model_provider_name == "openai"
        assert config.model_name == "openai_text_embedding_3_small"

    def test_chunk_embeddings_with_chunked_document_parent(self, mock_chunked_document):
        """Test ChunkEmbeddings with ChunkedDocument parent."""
        # Create embeddings for each chunk
        embeddings = []
        for chunk in mock_chunked_document.chunks:
            # Create a mock embedding (in real usage, this would be generated by the embedding model)
            embedding = Embedding(vector=[0.1, 0.2, 0.3, 0.4, 0.5])
            embeddings.append(embedding)

        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id="test-config-id",
            embeddings=embeddings,
            parent=mock_chunked_document,
        )
        assert chunk_embeddings.parent_chunked_document() == mock_chunked_document
        assert len(chunk_embeddings.embeddings) == len(mock_chunked_document.chunks)

    def test_embedding_workflow(self, mock_project, mock_chunked_document):
        """Test a complete embedding workflow."""
        # 1. Create an embedding config
        embedding_config = EmbeddingConfig(
            name="test-embedding-config",
            description="Test embedding configuration for workflow",
            model_provider_name="openai",
            model_name="openai_text_embedding_3_small",
            properties={"dimensions": 1536},
            parent=mock_project,
        )

        # 2. Create embeddings for the chunked document
        embeddings = []
        for chunk in mock_chunked_document.chunks:
            # Simulate embedding generation
            embedding = Embedding(vector=[0.1] * 1536)
            embeddings.append(embedding)

        # 3. Create chunk embeddings
        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id=embedding_config.id,
            embeddings=embeddings,
            parent=mock_chunked_document,
        )

        # 4. Verify the relationships
        assert embedding_config.parent_project() == mock_project
        assert chunk_embeddings.parent_chunked_document() == mock_chunked_document
        assert len(chunk_embeddings.embeddings) == len(mock_chunked_document.chunks)
        assert chunk_embeddings.embedding_config_id == embedding_config.id
