import tempfile
import uuid
from enum import Enum
from pathlib import Path

import pytest

from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import (
    Chunk,
    ChunkerConfig,
    ChunkerType,
    DocumentChunked,
    FixedWindowChunkerProperties,
)
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

    def test_default_values(self):
        """Test that default values are set correctly."""
        props = FixedWindowChunkerProperties()
        assert props.chunk_size == 256
        assert props.chunk_overlap == 10

    def test_custom_values(self):
        """Test that custom values can be set."""
        props = FixedWindowChunkerProperties(chunk_size=512, chunk_overlap=20)
        assert props.chunk_size == 512
        assert props.chunk_overlap == 20

    def test_validation_positive_values(self):
        """Test that positive values are accepted."""
        props = FixedWindowChunkerProperties(chunk_size=1, chunk_overlap=0)
        assert props.chunk_size == 1
        assert props.chunk_overlap == 0

    def test_validation_negative_values(self):
        """Test that negative values are rejected."""
        with pytest.raises(ValueError):
            FixedWindowChunkerProperties(chunk_size=-1, chunk_overlap=-1)

    def test_validation_overlap_greater_than_chunk_size(self):
        """Test that overlap is greater than chunk size."""
        with pytest.raises(ValueError):
            FixedWindowChunkerProperties(chunk_size=100, chunk_overlap=101)

    def test_validation_overlap_less_than_zero(self):
        """Test that overlap is less than zero."""
        with pytest.raises(ValueError):
            FixedWindowChunkerProperties(chunk_size=100, chunk_overlap=-1)


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

    def test_required_fields(self):
        """Test that required fields are properly validated."""
        # Should work with all required fields
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=FixedWindowChunkerProperties(),
        )
        assert config.name == "test-chunker"
        assert config.chunker_type == ChunkerType.FIXED_WINDOW
        assert isinstance(config.properties, FixedWindowChunkerProperties)

    def test_optional_description(self):
        """Test that description is optional."""
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=FixedWindowChunkerProperties(),
        )
        assert config.description is None

        config_with_desc = ChunkerConfig(
            name="test-chunker",
            description="A test chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=FixedWindowChunkerProperties(),
        )
        assert config_with_desc.description == "A test chunker"

    def test_name_validation(self):
        """Test name field validation."""
        # Test valid name
        config = ChunkerConfig(
            name="valid-name_123",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=FixedWindowChunkerProperties(),
        )
        assert config.name == "valid-name_123"

        # Test invalid name (contains special characters)
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="invalid@name",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties=FixedWindowChunkerProperties(),
            )

        # Test empty name
        with pytest.raises(ValueError):
            ChunkerConfig(
                name="",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties=FixedWindowChunkerProperties(),
            )

    def test_parent_project_method_no_parent(self):
        """Test parent_project method when no parent is set."""
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=FixedWindowChunkerProperties(),
        )
        assert config.parent_project() is None


class TestChunk:
    """Test the Chunk class."""

    def test_required_fields(self):
        """Test that required fields are properly validated."""
        # Create a temporary file for the attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            attachment = KilnAttachmentModel.from_file(tmp_path)
            chunk = Chunk(attachment=attachment)
            assert chunk.attachment == attachment

    def test_attachment_validation(self):
        """Test that attachment field is properly validated."""
        # Create a temporary file for the attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            # Test with valid attachment
            attachment = KilnAttachmentModel.from_file(tmp_path)
            chunk = Chunk(attachment=attachment)
            assert chunk.attachment == attachment

            # Test that attachment is required
            with pytest.raises(ValueError):
                Chunk(attachment=None)


class TestDocumentChunked:
    """Test the DocumentChunked class."""

    def test_required_fields(self):
        """Test that required fields are properly validated."""
        chunks = []
        doc = DocumentChunked(
            chunks=chunks, chunker_config_id="fake-id", name="test-document-chunked"
        )
        assert doc.chunks == chunks

    def test_with_chunks(self):
        """Test with actual chunks."""
        # Create a temporary file for the attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            attachment = KilnAttachmentModel.from_file(tmp_path)
            chunk1 = Chunk(attachment=attachment)
            chunk2 = Chunk(attachment=attachment)

            chunks = [chunk1, chunk2]
            doc = DocumentChunked(
                chunks=chunks, chunker_config_id="fake-id", name="test-document-chunked"
            )
            assert doc.chunks == chunks
            assert len(doc.chunks) == 2

    def test_parent_extraction_method_no_parent(self):
        """Test parent_extraction method when no parent is set."""
        doc = DocumentChunked(
            chunks=[], chunker_config_id="fake-id", name="test-document-chunked"
        )
        assert doc.parent_extraction() is None

    def test_empty_chunks_list(self):
        """Test that empty chunks list is valid."""
        doc = DocumentChunked(
            chunks=[], chunker_config_id="fake-id", name="test-document-chunked"
        )
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
            chunk = Chunk(attachment=attachment)
            chunks = [chunk]

            doc = DocumentChunked(
                chunks=chunks,
                chunker_config_id="fake-id",
                name="test-document-chunked",
            )
            assert doc.chunks == chunks

            # Test that chunks must be a list
            with pytest.raises(ValueError):
                DocumentChunked(
                    chunks=chunk,
                    chunker_config_id="fake-id",
                    name="test-document-chunked",
                )
