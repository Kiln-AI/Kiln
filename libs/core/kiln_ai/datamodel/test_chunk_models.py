import tempfile
import uuid
from enum import Enum
from pathlib import Path
from unittest.mock import patch

import pytest

from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument, ChunkerConfig, ChunkerType
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


class TestFixedWindowChunkerProperties:
    """Test the FixedWindowChunkerProperties class."""

    def test_required_fields(self):
        """Test that required fields are set correctly."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={},
            )

    def test_custom_values(self):
        """Test that custom values can be set."""
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={"chunk_size": 512, "chunk_overlap": 20},
        )
        assert config.properties == {
            "chunk_size": 512,
            "chunk_overlap": 20,
        }

        assert config.chunk_size() == 512
        assert config.chunk_overlap() == 20

    def test_validation_positive_values(self):
        """Test that positive values are accepted."""
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={"chunk_size": 1, "chunk_overlap": 0},
        )
        assert config.properties == {
            "chunk_size": 1,
            "chunk_overlap": 0,
        }

        assert config.chunk_size() == 1
        assert config.chunk_overlap() == 0

    def test_validation_negative_values(self):
        """Test that negative values are rejected."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": -1, "chunk_overlap": -1},
            )

    def test_validation_zero_chunk_size(self):
        """Test that zero chunk size is rejected."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": 0, "chunk_overlap": 0},
            )

    def test_validation_overlap_greater_than_chunk_size(self):
        """Test that overlap is greater than chunk size."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": 100, "chunk_overlap": 101},
            )

    def test_validation_overlap_less_than_zero(self):
        """Test that overlap is less than zero."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": 100, "chunk_overlap": -1},
            )

    def test_validation_overlap_without_chunk_size(self):
        """Test that overlap without chunk size is rejected."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_overlap": 10},
            )

    def test_validation_chunk_size_without_overlap(self):
        """Test that chunk size without overlap will raise an error."""
        with pytest.raises(ValueError, match=r"Chunk overlap is required."):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": 100},
            )

    def test_validation_wrong_type(self):
        """Test that wrong type is rejected."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": "100", "chunk_overlap": 10},
            )

    def test_validation_none_values(self):
        """Reject none values - we prefer not to have the properties rather than a None."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": None, "chunk_overlap": 15},  # type: ignore[arg-type]
            )


class TestSemanticChunkerProperties:
    """Test the Semantic Chunker properties validation."""

    def test_required_fields(self):
        """All required fields must be present for semantic chunker."""
        # missing embedding_config_id
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

        # missing buffer_size
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

        # missing breakpoint_percentile_threshold
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 2,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

        # missing include_metadata
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_prev_next_rel": True,
                },
            )

        # missing include_prev_next_rel
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                },
            )

    def test_invalid_buffer_size(self):
        """buffer_size must be >= 1."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 0,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

    def test_invalid_breakpoint_threshold(self):
        """breakpoint_percentile_threshold must be 0..100 inclusive."""
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 150,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

    def test_success(self):
        """Valid properties succeed."""
        cfg = ChunkerConfig(
            name="semantic",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "embedding_config_id": "emb-1",
                "buffer_size": 2,
                "breakpoint_percentile_threshold": 90,
                "include_metadata": False,
                "include_prev_next_rel": False,
            },
        )
        assert cfg.embedding_config_id() == "emb-1"


class TestChunkerType:
    """Test the ChunkerType enum."""

    def test_enum_values(self):
        """Test that enum has the expected values."""
        assert ChunkerType.FIXED_WINDOW == "fixed_window"

    def test_enum_inheritance(self):
        """Test that ChunkerType inherits from str and Enum."""
        assert issubclass(ChunkerType, str)
        assert issubclass(ChunkerType, Enum)

    def test_enum_comparison(self):
        """Test enum comparison operations."""
        assert ChunkerType.FIXED_WINDOW == "fixed_window"
        assert ChunkerType.FIXED_WINDOW.value == "fixed_window"


class TestChunkerConfig:
    """Test the ChunkerConfig class."""

    def test_optional_description(self):
        """Test that description is optional."""
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={
                "chunk_size": 100,
                "chunk_overlap": 10,
            },
        )
        assert config.description is None

        config_with_desc = ChunkerConfig(
            name="test-chunker",
            description="A test chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={
                "chunk_size": 100,
                "chunk_overlap": 10,
            },
        )
        assert config_with_desc.description == "A test chunker"

    def test_name_validation(self):
        """Test name field validation."""
        # Test valid name
        config = ChunkerConfig(
            name="valid-name_123",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={
                "chunk_size": 100,
                "chunk_overlap": 10,
            },
        )
        assert config.name == "valid-name_123"

        # Test invalid name (contains special characters)
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="invalid@name",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={},
            )

        # Test empty name
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={},
            )

    def test_parent_project_method_no_parent(self):
        """Test parent_project method when no parent is set."""
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={
                "chunk_size": 100,
                "chunk_overlap": 10,
            },
        )
        assert config.parent_project() is None


class TestChunk:
    """Test the Chunk class."""

    def test_required_fields(self):
        """Test that required fields are properly validated."""
        # Create a temporary file for the content
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            attachment = KilnAttachmentModel.from_file(tmp_path)
            chunk = Chunk(content=attachment)
            assert chunk.content == attachment

    def test_content_validation(self):
        """Test that content field is properly validated."""
        # Create a temporary file for the attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            # Test with valid attachment
            attachment = KilnAttachmentModel.from_file(tmp_path)
            chunk = Chunk(content=attachment)
            assert chunk.content == attachment

            # Test that attachment is required
            with pytest.raises(ValueError):
                Chunk(content=None)  # type: ignore[arg-type]


class TestChunkedDocument:
    """Test the ChunkedDocument class."""

    def test_required_fields(self):
        """Test that required fields are properly validated."""
        chunks = []
        doc = ChunkedDocument(chunks=chunks, chunker_config_id="fake-id")
        assert doc.chunks == chunks

    def test_with_chunks(self):
        """Test with actual chunks."""
        # Create a temporary file for the attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            attachment = KilnAttachmentModel.from_file(tmp_path)
            chunk1 = Chunk(content=attachment)
            chunk2 = Chunk(content=attachment)

            chunks = [chunk1, chunk2]
            doc = ChunkedDocument(chunks=chunks, chunker_config_id="fake-id")
            assert doc.chunks == chunks
            assert len(doc.chunks) == 2

    def test_parent_extraction_method_no_parent(self):
        """Test parent_extraction method when no parent is set."""
        doc = ChunkedDocument(chunks=[], chunker_config_id="fake-id")
        assert doc.parent_extraction() is None

    def test_empty_chunks_list(self):
        """Test that empty chunks list is valid."""
        doc = ChunkedDocument(chunks=[], chunker_config_id="fake-id")
        assert doc.chunks == []
        assert len(doc.chunks) == 0

    def test_chunks_validation(self):
        """Test that chunks field validation works correctly."""
        # Create a temporary file for the attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            # Test with valid list of chunks
            attachment = KilnAttachmentModel.from_file(tmp_path)
            chunk = Chunk(content=attachment)
            chunks = [chunk]

            doc = ChunkedDocument(
                chunks=chunks,
                chunker_config_id="fake-id",
            )
            assert doc.chunks == chunks

            # Test that chunks must be a list
            with pytest.raises(ValueError):
                ChunkedDocument(
                    chunks=chunk,  # type: ignore[arg-type]
                    chunker_config_id="fake-id",
                )


def test_chunk_serialize_content_uses_prefix(tmp_path):
    att = KilnAttachmentModel.from_data("hello", "text/plain")
    chunk = Chunk(content=att)
    # emulate model_dump with context used in Chunk.field_serializer
    data = chunk.model_dump(
        mode="json", context={"filename_prefix": "content", "save_attachments": False}
    )
    assert "content" in data


@pytest.mark.asyncio
async def test_chunked_document_load_chunks_text_errors_when_no_path(tmp_path):
    doc = ChunkedDocument(
        chunker_config_id="cfg",
        chunks=[
            Chunk(content=KilnAttachmentModel.from_data("a", "text/plain")),
        ],
    )
    with pytest.raises(ValueError, match="does not have a path"):
        await doc.load_chunks_text()


@pytest.mark.asyncio
async def test_chunked_document_load_chunks_text_read_failure(tmp_path):
    # Build a chunked doc and force read failure by mocking read_text
    bad_attachment = KilnAttachmentModel.from_data("x", "text/plain")
    chunked = ChunkedDocument(
        chunker_config_id="cfg",
        chunks=[Chunk(content=bad_attachment)],
    )
    # set a fake path so load_chunks_text passes initial path check
    chunked.path = tmp_path / "dummy" / "doc.kiln"

    # mock anyio.Path.read_text to raise
    async def fail_read_text(self, encoding="utf-8"):
        raise RuntimeError("boom")

    with patch(
        "kiln_ai.datamodel.chunk.anyio.Path.read_text",
        new=fail_read_text,
    ):
        with pytest.raises(ValueError, match="Failed to read chunk content"):
            await chunked.load_chunks_text()


class TestSemanticChunkerPropertiesTypes:
    def test_invalid_types(self):
        with pytest.raises(ValueError, match="embedding_config_id must be a string"):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": 123,
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

        with pytest.raises(ValueError, match="buffer_size must be an integer"):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": "2",
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

        with pytest.raises(
            ValueError, match="breakpoint_percentile_threshold must be an integer"
        ):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": "90",
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            )

        with pytest.raises(ValueError, match="include_metadata must be a boolean"):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": "yes",
                    "include_prev_next_rel": True,
                },
            )

        with pytest.raises(ValueError, match="include_prev_next_rel must be a boolean"):
            ChunkerConfig(
                name="semantic",
                chunker_type=ChunkerType.SEMANTIC,
                properties={
                    "embedding_config_id": "emb-1",
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                    "include_prev_next_rel": "yes",
                },
            )


class TestChunkerConfigGetterValidations:
    def test_getter_type_errors(self):
        cfg = ChunkerConfig(
            name="fixed",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={"chunk_size": 100, "chunk_overlap": 10},
        )
        # mutate to wrong types to exercise getters
        cfg.properties["chunk_size"] = "100"
        with pytest.raises(ValueError, match="Chunk size must be an integer"):
            cfg.chunk_size()
        cfg.properties["chunk_size"] = 100

        cfg.properties["chunk_overlap"] = "10"
        with pytest.raises(ValueError, match="Chunk overlap must be an integer"):
            cfg.chunk_overlap()
        cfg.properties["chunk_overlap"] = 10

        # semantic getters
        scfg = ChunkerConfig(
            name="semantic",
            chunker_type=ChunkerType.SEMANTIC,
            properties={
                "embedding_config_id": "emb",
                "buffer_size": 2,
                "breakpoint_percentile_threshold": 50,
                "include_metadata": True,
                "include_prev_next_rel": False,
            },
        )

        scfg.properties["embedding_config_id"] = 1
        with pytest.raises(ValueError, match="embedding_config_id must be a string"):
            scfg.embedding_config_id()
        scfg.properties["embedding_config_id"] = "emb"

        scfg.properties["buffer_size"] = "2"
        with pytest.raises(ValueError, match="Buffer size must be an integer"):
            scfg.buffer_size()
        scfg.properties["buffer_size"] = 2

        scfg.properties["breakpoint_percentile_threshold"] = "50"
        with pytest.raises(
            ValueError, match="Breakpoint percentile threshold must be an integer"
        ):
            scfg.breakpoint_percentile_threshold()
        scfg.properties["breakpoint_percentile_threshold"] = -1
        with pytest.raises(ValueError, match="between 0 and 100"):
            scfg.breakpoint_percentile_threshold()
        scfg.properties["breakpoint_percentile_threshold"] = 150
        with pytest.raises(ValueError, match="between 0 and 100"):
            scfg.breakpoint_percentile_threshold()
        scfg.properties["breakpoint_percentile_threshold"] = 50

        scfg.properties["include_metadata"] = "true"
        with pytest.raises(ValueError, match="Include metadata must be a boolean"):
            scfg.include_metadata()
        scfg.properties["include_metadata"] = True

        scfg.properties["include_prev_next_rel"] = "false"
        with pytest.raises(ValueError, match="Include prev next rel must be a boolean"):
            scfg.include_prev_next_rel()
        scfg.properties["include_prev_next_rel"] = False
