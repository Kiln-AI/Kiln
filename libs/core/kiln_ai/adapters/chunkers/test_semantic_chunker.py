"""Tests for semantic chunker."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiln_ai.adapters.chunkers.semantic_chunker import SemanticChunker
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.project import Project


@pytest.fixture
def semantic_chunker_config() -> ChunkerConfig:
    """Create a semantic chunker config for testing."""
    return ChunkerConfig(
        name="test-semantic-chunker",
        chunker_type=ChunkerType.SEMANTIC,
        properties={
            "embedding_config_id": "emb-123",
            "buffer_size": 2,
            "breakpoint_percentile_threshold": 90,
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
    mock_splitter.abuild_semantic_nodes_from_documents = AsyncMock(
        return_value=[mock_node1, mock_node2]
    )
    return mock_splitter


@pytest.fixture
def semantic_chunker_factory():
    """Factory for creating semantic chunkers with mocked dependencies."""

    def create_chunker(config: ChunkerConfig) -> SemanticChunker:
        with (
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.KilnEmbeddingWrapper"
            ) as mock_wrapper_class,
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.SemanticSplitterNodeParser"
            ) as mock_splitter_class,
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.EmbeddingConfig.from_id_and_parent_path"
            ) as mock_from,
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.embedding_adapter_from_type"
            ) as mock_adapter,
        ):
            proj = Project(name="p")
            proj.path = Path("/tmp")
            config.parent = proj

            # Create mock embedding wrapper
            mock_wrapper = MagicMock()
            mock_wrapper_class.return_value = mock_wrapper
            mock_from.return_value = MagicMock()
            mock_adapter.return_value = MagicMock()

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

    def test_init_missing_embedding_config_id(self, semantic_chunker_factory):
        """Test that missing embedding_config_id raises ValueError."""
        with pytest.raises(
            ValueError, match="embedding_config_id is required for semantic chunker"
        ):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "buffer_size": 1,
                },
            )

    def test_init_resolves_embedding_config(
        self, semantic_chunker_factory, semantic_chunker_config, monkeypatch
    ):
        """Test that a valid embedding_config_id is resolved from project path."""

        # attach fake project
        proj = Project(name="p", path=Path("/tmp"))
        semantic_chunker_config.parent = proj
        # mock resolver
        with patch(
            "kiln_ai.adapters.chunkers.semantic_chunker.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_from:
            mock_from.return_value = MagicMock()
            with patch(
                "kiln_ai.adapters.embedding.embedding_registry.embedding_adapter_from_type"
            ) as mock_adapter:
                mock_adapter.return_value = MagicMock()
                semantic_chunker_factory(semantic_chunker_config)

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
                "kiln_ai.adapters.chunkers.semantic_chunker.KilnEmbeddingWrapper"
            ) as mock_wrapper_class,
            patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.SemanticSplitterNodeParser"
            ) as mock_splitter_class,
        ):
            # Setup mocks
            mock_wrapper = MagicMock()
            mock_wrapper_class.return_value = mock_wrapper
            mock_splitter_class.return_value = mock_semantic_splitter

            # attach project and mock embedding config resolution
            from pathlib import Path

            from kiln_ai.datamodel.project import Project

            proj = Project(name="p")
            proj.path = Path("/tmp")
            semantic_chunker_config.parent = proj
            with patch(
                "kiln_ai.adapters.chunkers.semantic_chunker.EmbeddingConfig.from_id_and_parent_path"
            ) as mock_from:
                mock_from.return_value = MagicMock()
                with patch(
                    "kiln_ai.adapters.chunkers.semantic_chunker.embedding_adapter_from_type"
                ) as mock_adapter:
                    mock_adapter.return_value = MagicMock()
                    chunker = SemanticChunker(semantic_chunker_config)
            result = await chunker._chunk(
                "This is a test document with multiple sentences."
            )

            # Verify the semantic splitter was called
            mock_semantic_splitter.abuild_semantic_nodes_from_documents.assert_called_once()

            # Verify the result
            assert len(result.chunks) == 2
            assert result.chunks[0].text == "First semantic chunk."
            assert result.chunks[1].text == "Second semantic chunk."

    def test_chunker_config_properties(self, semantic_chunker_config):
        """Test that chunker config properties are correctly accessed."""
        assert semantic_chunker_config.embedding_config_id() == "emb-123"
        assert semantic_chunker_config.buffer_size() == 2
        assert semantic_chunker_config.breakpoint_percentile_threshold() == 90
        assert semantic_chunker_config.include_metadata() is True
        assert semantic_chunker_config.include_prev_next_rel() is True

    def test_chunker_config_optional_properties_none(self):
        """Test that optional properties return None when not set."""
        config = ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "embedding_config_id": "emb-123",
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
        with pytest.raises(ValueError, match="embedding_config_id is required"):
            ChunkerConfig(
                name="test",
                chunker_type=ChunkerType.SEMANTIC,
                properties={},
            )

    def test_validation_missing_model_provider_name(self):
        """Test validation fails when model_provider_name is missing."""
        # not applicable anymore
        ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "embedding_config_id": "emb-1",
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
                    "embedding_config_id": "emb-1",
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
                    "embedding_config_id": "emb-1",
                    "breakpoint_percentile_threshold": 150,
                },
            )

    def test_validation_success(self):
        """Test validation succeeds with valid properties."""
        config = ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "embedding_config_id": "emb-1",
                "buffer_size": 2,
                "breakpoint_percentile_threshold": 90,
                "include_metadata": False,
                "include_prev_next_rel": False,
            },
        )
        # Should not raise any exception
        assert config.embedding_config_id() == "emb-1"

    def test_validation_optional_properties_not_required(self):
        """Test that optional properties are not required."""
        config = ChunkerConfig(
            name="test",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "embedding_config_id": "emb-1",
            },
        )
        # Should not raise any exception
        assert config.embedding_config_id() == "emb-1"


@pytest.mark.paid
async def test_semantic_chunker_real_integration(tmp_path):
    """Paid test: run SemanticChunker end-to-end with a real embedding model."""

    # Create a minimal project
    project = Project(name="p", path=Path(tmp_path) / "project.kiln")
    project.save_to_file()

    # Create and persist a real embedding config (OpenAI small model is cheap)
    embedding_config = EmbeddingConfig(
        parent=project,
        name="paid-test-emb",
        description=None,
        model_provider_name=ModelProviderName.openai,
        model_name="openai_text_embedding_3_small",
        properties={},
    )
    embedding_config.save_to_file()

    # Build a semantic chunker config referencing the real embedding config
    chunker_config = ChunkerConfig(
        parent=project,
        name="paid-test-semantic",
        chunker_type=ChunkerType.SEMANTIC,
        properties={
            "embedding_config_id": str(embedding_config.id),
            "buffer_size": 2,
            "breakpoint_percentile_threshold": 80,
            "include_metadata": False,
            "include_prev_next_rel": False,
        },
    )
    chunker_config.save_to_file()

    chunker = SemanticChunker(chunker_config)

    # Short text to keep costs minimal
    text = [
        # random paragraphs generated by ChatGPT - the idea is they are about very different topics so should
        # get split into different chunks - this is flaky so test may fail sometimes
        "The history of spices is, in many ways, the history of globalization itself. Centuries before modern trade routes, nutmeg, cinnamon, and pepper were worth their weight in gold, fueling voyages that would reshape the world map. The pursuit of these fragrant commodities drove European explorers eastward, leading to colonization, maritime warfare, and the emergence of global empires. Ironically, what began as a quest for flavor—something so trivial and sensory—ended up redrawing borders, exterminating civilizations, and kickstarting capitalism as we know it. Every pinch of pepper on a modern dinner table is, in a sense, a quiet echo of empire and bloodshed.",
        "In an entirely different domain, the psychology of social media addiction mirrors that of slot machines more than many realize. Platforms like TikTok and Instagram deploy variable-ratio reward schedules—the same mechanism casinos use—where a user never knows when the next “hit” of validation will come. This unpredictability keeps people scrolling endlessly, tethered to microbursts of dopamine. What's sinister is that these systems adapt to each user's emotional state, leveraging vast datasets to fine-tune the timing of rewards. It's not just distraction—it's engineered compulsion, dressed up as connection.",
        "Meanwhile, in astrophysics, the concept of dark matter remains one of the most haunting mysteries of the universe. We can't see it, touch it, or detect it directly, yet it shapes everything we observe. Galaxies rotate too fast for their visible mass; something unseen must be holding them together. Physicists estimate that nearly 85% of the universe's matter is this invisible substance. It's like knowing there's a ghost in the room because your furniture keeps moving—but never being able to catch it in the act. Dark matter humbles human arrogance: we understand the cosmos only through the faint outlines of what we cannot see.",
    ]

    result = await chunker.chunk(" ".join(text))

    # Basic sanity assertions
    assert len(result.chunks) >= 1
    assert all(isinstance(c.text, str) and len(c.text) > 0 for c in result.chunks)

    assert (
        "The history of spices is, in many ways, the history of globalization itself."
        in result.chunks[0].text
    )

    # flaky assertion, may fail sometimes
    assert len(result.chunks) >= 3
