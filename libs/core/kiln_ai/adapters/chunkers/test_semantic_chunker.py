"""Tests for semantic chunker."""

from unittest.mock import MagicMock, patch

import pytest

from kiln_ai.adapters.chunkers.semantic_chunker import SemanticChunker
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType


@pytest.fixture
def semantic_chunker_config() -> ChunkerConfig:
    """Create a semantic chunker config for testing."""
    return ChunkerConfig(
        name="test-semantic-chunker",
        chunker_type=ChunkerType.SEMANTIC,
        properties={
            "model_provider": "text-embedding-3-small",
            "model_provider_name": "openai",
            "buffer_size": 2,
            "breakpoint_percentile_threshold": 90.0,
            "include_metadata": True,
            "include_prev_next_rel": True,
        },
    )


@pytest.fixture
def mock_embedding_wrapper():
    """Create a mock embedding wrapper."""
    mock_wrapper = MagicMock()
    mock_wrapper._get_text_embedding_batch = MagicMock(
        return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]
    )
    return mock_wrapper


@pytest.fixture
def mock_semantic_splitter():
    """Create a mock semantic splitter."""
    mock_splitter = MagicMock()
    mock_node1 = MagicMock()
    mock_node1.get_content.return_value = "First semantic chunk."
    mock_node2 = MagicMock()
    mock_node2.get_content.return_value = "Second semantic chunk."
    mock_splitter.build_semantic_nodes_from_documents.return_value = [
        mock_node1,
        mock_node2,
    ]
    return mock_splitter


@pytest.fixture
def semantic_chunker_factory():
    """Factory for creating semantic chunkers with mocked dependencies."""

    def create_chunker(config: ChunkerConfig) -> SemanticChunker:
        with (
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.create_embedding_wrapper"
            ) as mock_create_wrapper,
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.SemanticSplitterNodeParser"
            ) as mock_splitter_class,
        ):
            # Create mock embedding wrapper
            mock_wrapper = MagicMock()
            mock_create_wrapper.return_value = mock_wrapper

            # Create mock semantic splitter
            mock_splitter = MagicMock()
            mock_splitter_class.return_value = mock_splitter

            return SemanticChunker(config)

    return create_chunker


class TestSemanticChunker:
    """Test the SemanticChunker class."""

    def test_init_wrong_chunker_type(self, semantic_chunker_factory):
        """Test that wrong chunker type raises ValueError."""
        config = ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={"chunk_size": 100, "chunk_overlap": 10},
        )

        with pytest.raises(ValueError, match="Chunker type must be SEMANTIC"):
            semantic_chunker_factory(config)

    def test_init_missing_model_provider(self, semantic_chunker_factory):
        """Test that missing model provider raises ValueError."""
        with pytest.raises(
            ValueError, match="model_provider is required for semantic chunker"
        ):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "model_provider_name": "openai",
                    "buffer_size": 1,
                },
            )

    def test_init_missing_model_provider_name(self, semantic_chunker_factory):
        """Test that missing model provider name raises ValueError."""
        with pytest.raises(
            ValueError, match="model_provider_name is required for semantic chunker"
        ):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "model_provider": "text-embedding-3-small",
                    "buffer_size": 1,
                },
            )

    def test_init_success(self, semantic_chunker_factory, semantic_chunker_config):
        """Test successful initialization."""
        chunker = semantic_chunker_factory(semantic_chunker_config)
        assert chunker.chunker_config == semantic_chunker_config

    @pytest.mark.asyncio
    async def test_chunk_empty_text(
        self, semantic_chunker_factory, semantic_chunker_config
    ):
        """Test chunking empty text returns empty result."""
        chunker = semantic_chunker_factory(semantic_chunker_config)
        result = await chunker.chunk("")
        assert result.chunks == []

    @pytest.mark.asyncio
    async def test_chunk_success(
        self, semantic_chunker_factory, semantic_chunker_config, mock_semantic_splitter
    ):
        """Test successful chunking."""
        with (
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.create_embedding_wrapper"
            ) as mock_create_wrapper,
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.SemanticSplitterNodeParser"
            ) as mock_splitter_class,
        ):
            # Setup mocks
            mock_wrapper = MagicMock()
            mock_create_wrapper.return_value = mock_wrapper
            mock_splitter_class.return_value = mock_semantic_splitter

            chunker = SemanticChunker(semantic_chunker_config)
            result = await chunker._chunk(
                "This is a test document with multiple sentences."
            )

            # Verify the semantic splitter was called
            mock_semantic_splitter.build_semantic_nodes_from_documents.assert_called_once()

            # Verify the result
            assert len(result.chunks) == 2
            assert result.chunks[0].text == "First semantic chunk."
            assert result.chunks[1].text == "Second semantic chunk."

    def test_chunker_config_properties(self, semantic_chunker_config):
        """Test that chunker config properties are correctly accessed."""
        assert semantic_chunker_config.model_provider() == "text-embedding-3-small"
        assert semantic_chunker_config.model_provider_name() == "openai"
        assert semantic_chunker_config.buffer_size() == 2
        assert semantic_chunker_config.breakpoint_percentile_threshold() == 90.0
        assert semantic_chunker_config.include_metadata() is True
        assert semantic_chunker_config.include_prev_next_rel() is True

    def test_chunker_config_optional_properties_none(self):
        """Test that optional properties return None when not set."""
        config = ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "model_provider": "text-embedding-3-small",
                "model_provider_name": "openai",
            },
        )

        assert config.buffer_size() is None
        assert config.breakpoint_percentile_threshold() is None
        assert config.include_metadata() is None
        assert config.include_prev_next_rel() is None


class TestSemanticChunkerValidation:
    """Test validation for semantic chunker properties."""

    def test_validation_missing_model_provider(self):
        """Test validation fails when model_provider is missing."""
        with pytest.raises(ValueError, match="model_provider is required"):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "model_provider_name": "openai",
                },
            )

    def test_validation_missing_model_provider_name(self):
        """Test validation fails when model_provider_name is missing."""
        with pytest.raises(ValueError, match="model_provider_name is required"):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "model_provider": "text-embedding-3-small",
                },
            )

    def test_validation_invalid_buffer_size(self):
        """Test validation fails when buffer_size is invalid."""
        with pytest.raises(
            ValueError, match="buffer_size must be greater than or equal to 1"
        ):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "model_provider": "text-embedding-3-small",
                    "model_provider_name": "openai",
                    "buffer_size": 0,
                },
            )

    def test_validation_invalid_breakpoint_threshold(self):
        """Test validation fails when breakpoint_percentile_threshold is invalid."""
        with pytest.raises(
            ValueError,
            match="breakpoint_percentile_threshold must be between 0 and 100",
        ):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "model_provider": "text-embedding-3-small",
                    "model_provider_name": "openai",
                    "breakpoint_percentile_threshold": 150,
                },
            )

    def test_validation_success(self):
        """Test validation succeeds with valid properties."""
        config = ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "model_provider": "text-embedding-3-small",
                "model_provider_name": "openai",
                "buffer_size": 2,
                "breakpoint_percentile_threshold": 90.0,
                "include_metadata": False,
                "include_prev_next_rel": False,
            },
        )
        # Should not raise any exception
        assert config.model_provider() == "text-embedding-3-small"
        assert config.model_provider_name() == "openai"
        assert config.buffer_size() == 2
        assert config.breakpoint_percentile_threshold() == 90.0
        assert config.include_metadata() is False
        assert config.include_prev_next_rel() is False

    def test_validation_optional_properties_not_required(self):
        """Test that optional properties are not required."""
        config = ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "model_provider": "text-embedding-3-small",
                "model_provider_name": "openai",
            },
        )
        # Should not raise any exception
        assert config.model_provider() == "text-embedding-3-small"
        assert config.model_provider_name() == "openai"
