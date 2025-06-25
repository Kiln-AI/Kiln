import tempfile
import uuid
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
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractionSource,
    FileInfo,
    Kind,
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


class TestIntegration:
    """Integration tests for the chunk module."""

    def test_full_workflow(self):
        """Test a complete workflow with all classes."""
        # Create chunker properties
        properties = FixedWindowChunkerProperties(chunk_size=256, chunk_overlap=10)

        # Create chunker config
        config = ChunkerConfig(
            name="test-chunker",
            description="A test chunker configuration",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=properties,
        )

        # Create a temporary file for the attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

            # Create attachment
            attachment = KilnAttachmentModel.from_file(tmp_path)

            # Create chunks
            chunk1 = Chunk(attachment=attachment)
            chunk2 = Chunk(attachment=attachment)

            # Create chunk document
            doc = DocumentChunked(
                chunks=[chunk1, chunk2],
                chunker_config_id=config.id,
                name="test-document-chunked",
            )

            # Verify the complete structure
            assert config.name == "test-chunker"
            assert config.chunker_type == ChunkerType.FIXED_WINDOW
            assert config.properties.chunk_size == 256
            assert len(doc.chunks) == 2
            assert doc.chunks[0].attachment == attachment
            assert doc.chunks[1].attachment == attachment

    def test_serialization(self, mock_project):
        """Test that models can be serialized and deserialized."""
        properties = FixedWindowChunkerProperties(chunk_size=512, chunk_overlap=20)
        config = ChunkerConfig(
            name="serialization-test",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=properties,
            parent=mock_project,
        )

        # Save to file
        config.save_to_file()

        # Load from file
        config_restored = ChunkerConfig.load_from_file(config.path)

        assert config_restored.name == config.name
        assert config_restored.chunker_type == config.chunker_type
        assert config_restored.properties.chunk_size == config.properties.chunk_size
        assert (
            config_restored.properties.chunk_overlap == config.properties.chunk_overlap
        )
        assert config_restored.parent_project().id == mock_project.id

    def test_enum_serialization(self):
        """Test that ChunkerType enum serializes correctly."""
        config = ChunkerConfig(
            name="enum-test",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=FixedWindowChunkerProperties(),
        )

        config_dict = config.model_dump()
        assert config_dict["chunker_type"] == "fixed_window"

        config_restored = ChunkerConfig.model_validate(config_dict)
        assert config_restored.chunker_type == ChunkerType.FIXED_WINDOW

    def test_relationships(self, mock_project):
        """Test that relationships are properly validated."""

        # Create a config
        config = ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties=FixedWindowChunkerProperties(),
            parent=mock_project,
        )
        config.save_to_file()

        # Dummy file we will use as attachment
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = Path(tmp_file.name)

        # Create a document
        document = Document(
            name="test-document",
            description="Test document",
            parent=mock_project,
            original_file=FileInfo(
                filename="test.txt",
                size=100,
                mime_type="text/plain",
                attachment=KilnAttachmentModel.from_file(tmp_path),
            ),
            kind=Kind.DOCUMENT,
        )
        document.save_to_file()

        # Create an extraction
        extraction = Extraction(
            source=ExtractionSource.PROCESSED,
            extractor_config_id=config.id,
            output=KilnAttachmentModel.from_file(tmp_path),
            parent=document,
        )
        extraction.save_to_file()

        # Create some chunks
        chunks = [Chunk(attachment=KilnAttachmentModel.from_file(tmp_path))] * 3

        document_chunked = DocumentChunked(
            parent=extraction,
            chunks=chunks,
            chunker_config_id=config.id,
            name="test-document-chunked",
            description="Test document chunked",
        )
        document_chunked.save_to_file()

        # Check that the document chunked is associated with the correct extraction
        assert document_chunked.parent_extraction().id == extraction.id

        for document_chunked_found in extraction.documents_chunked():
            assert document_chunked.id == document_chunked_found.id

        assert len(extraction.documents_chunked()) == 1
