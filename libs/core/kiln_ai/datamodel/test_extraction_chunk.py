import tempfile
import uuid
from pathlib import Path

import pytest

from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument, ChunkerConfig, ChunkerType
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
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
        properties = {"chunk_size": 256, "chunk_overlap": 10}

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
            chunk1 = Chunk(content=attachment)
            chunk2 = Chunk(content=attachment)

            # Create chunk document
            doc = ChunkedDocument(
                chunks=[chunk1, chunk2],
                chunker_config_id=config.id,
            )

            # Verify the complete structure
            assert config.name == "test-chunker"
            assert config.chunker_type == ChunkerType.FIXED_WINDOW
            assert config.chunk_size() == 256
            assert config.chunk_overlap() == 10
            assert len(doc.chunks) == 2
            assert doc.chunks[0].content == attachment
            assert doc.chunks[1].content == attachment

    def test_serialization(self, mock_project):
        """Test that models can be serialized and deserialized."""
        properties = {"chunk_size": 512, "chunk_overlap": 20}
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
        assert config_restored.chunk_size() == config.chunk_size()
        assert config_restored.chunk_overlap() == config.chunk_overlap()
        assert config_restored.parent_project().id == mock_project.id

    def test_enum_serialization(self):
        """Test that ChunkerType enum serializes correctly."""
        config = ChunkerConfig(
            name="enum-test",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={"chunk_size": 512, "chunk_overlap": 20},
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
            properties={"chunk_size": 512, "chunk_overlap": 20},
            parent=mock_project,
        )
        config.save_to_file()

        # Dummy file we will use as attachment
        with tempfile.NamedTemporaryFile(delete=True) as tmp_file:
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
            chunks = [Chunk(content=KilnAttachmentModel.from_file(tmp_path))] * 3

            chunked_document = ChunkedDocument(
                parent=extraction,
                chunks=chunks,
                chunker_config_id=config.id,
            )
            chunked_document.save_to_file()

            assert len(chunked_document.chunks) == 3

            # Check that the document chunked is associated with the correct extraction
            assert chunked_document.parent_extraction().id == extraction.id

            for chunked_document_found in extraction.chunked_documents():
                assert chunked_document.id == chunked_document_found.id

            assert len(extraction.chunked_documents()) == 1

            # the chunks should have a filename prefixed with content_
            for chunk in chunked_document.chunks:
                filename = chunk.content.path.name
                assert filename.startswith("content_")

            # create an embedding config
            embedding_config = EmbeddingConfig(
                name="test-embedding-config",
                description="Test embedding config",
                parent=mock_project,
                model_name="openai_text_embedding_3_small",
                model_provider_name="openai",
                properties={},
            )
            embedding_config.save_to_file()

            # create chunk embeddings
            chunk_embeddings = ChunkEmbeddings(
                parent=chunked_document,
                embedding_config_id=embedding_config.id,
                embeddings=[Embedding(vector=[1.0] * 1536) for _ in range(3)],
            )
            chunk_embeddings.save_to_file()

            retrieved_chunk_embeddings = chunked_document.chunk_embeddings()
            assert isinstance(retrieved_chunk_embeddings, list)
            assert len(retrieved_chunk_embeddings) == 1

            # check project has the embedding config and the chunker config
            assert (
                mock_project.embedding_configs(readonly=True)[0].id
                == embedding_config.id
            )
            assert mock_project.chunker_configs(readonly=True)[0].id == config.id
