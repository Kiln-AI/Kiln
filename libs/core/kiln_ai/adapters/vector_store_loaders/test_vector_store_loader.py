import uuid
from dataclasses import dataclass

import pytest

from kiln_ai.adapters.vector_store_loaders.vector_store_loader import VectorStoreLoader
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.datamodel_enums import KilnMimeType
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractionSource,
    FileInfo,
    Kind,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig


@dataclass
class DocWithChunks:
    document: Document
    extraction: Extraction
    chunked_document: ChunkedDocument
    chunked_embeddings: ChunkEmbeddings


def lorem_ipsum(n: int) -> str:
    return " ".join(
        ["Lorem ipsum dolor sit amet, consectetur adipiscing elit." for _ in range(n)]
    )


@pytest.fixture
def mock_chunks_factory(mock_attachment_factory):
    def fn(
        project: Project,
        rag_config: RagConfig,
        num_chunks: int = 1,
        text: str | None = None,
        extractor_config_id: str | None = None,
        chunker_config_id: str | None = None,
        embedding_config_id: str | None = None,
    ) -> DocWithChunks:
        doc = Document(
            id=f"doc_{uuid.uuid4()}",
            name="Test Document",
            description="Test Document",
            original_file=FileInfo(
                filename="test.pdf",
                size=100,
                mime_type="application/pdf",
                attachment=mock_attachment_factory(KilnMimeType.PDF),
            ),
            kind=Kind.DOCUMENT,
            parent=project,
        )
        doc.save_to_file()

        extraction = Extraction(
            source=ExtractionSource.PROCESSED,
            extractor_config_id=extractor_config_id or rag_config.extractor_config_id,
            output=mock_attachment_factory(KilnMimeType.PDF),
            parent=doc,
        )
        extraction.save_to_file()

        chunks = [
            Chunk(
                content=mock_attachment_factory(
                    KilnMimeType.TXT, text=f"text-{i}: {text or lorem_ipsum(10)}"
                )
            )
            for i in range(num_chunks)
        ]
        chunked_document = ChunkedDocument(
            chunks=chunks,
            chunker_config_id=chunker_config_id or rag_config.chunker_config_id,
            parent=extraction,
        )
        chunked_document.save_to_file()
        chunked_embeddings = ChunkEmbeddings(
            embeddings=[
                Embedding(vector=[i + 0.1, i + 0.2, i + 0.3, i + 0.4, i + 0.5])
                for i in range(num_chunks)
            ],
            embedding_config_id=embedding_config_id or rag_config.embedding_config_id,
            parent=chunked_document,
        )
        chunked_embeddings.save_to_file()
        return DocWithChunks(
            document=doc,
            extraction=extraction,
            chunked_document=chunked_document,
            chunked_embeddings=chunked_embeddings,
        )

    return fn


@pytest.fixture
def mock_project(tmp_path):
    project = Project(
        name="Test Project", path=tmp_path / "test_project" / "project.kiln"
    )
    project.save_to_file()
    return project


@pytest.fixture
def rag_config_factory(mock_project):
    def fn(
        extractor_config_id: str = "test_extractor",
        chunker_config_id: str = "test_chunker",
        embedding_config_id: str = "test_embedding",
    ) -> RagConfig:
        rag_config = RagConfig(
            name="Test Rag Config",
            parent=mock_project,
            vector_store_config_id="test_vector_store",
            tool_name="test_tool",
            tool_description="test_description",
            extractor_config_id=extractor_config_id,
            chunker_config_id=chunker_config_id,
            embedding_config_id=embedding_config_id,
        )
        rag_config.save_to_file()
        return rag_config

    return fn


# Tests for VectorStoreLoader.iter_llama_index_nodes


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_single_document(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test iter_llama_index_nodes with a single document that matches all config IDs."""
    rag_config = rag_config_factory()
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create a document with chunks
    doc_with_chunks = mock_chunks_factory(
        mock_project, rag_config, num_chunks=3, text="Test content"
    )

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    assert len(all_nodes) == 3
    # Check that all nodes have the correct document ID
    for node in all_nodes:
        assert node.metadata["kiln_doc_id"] == str(doc_with_chunks.document.id)
        assert "kiln_chunk_idx" in node.metadata
        assert "text" in node.text


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_multiple_documents(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test iter_llama_index_nodes with multiple documents."""
    rag_config = rag_config_factory()
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create multiple documents
    doc1 = mock_chunks_factory(mock_project, rag_config, num_chunks=2, text="Doc 1")
    doc2 = mock_chunks_factory(mock_project, rag_config, num_chunks=3, text="Doc 2")
    doc3 = mock_chunks_factory(mock_project, rag_config, num_chunks=1, text="Doc 3")

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    assert len(all_nodes) == 6  # 2 + 3 + 1 = 6 total chunks

    # Group nodes by document ID
    nodes_by_doc = {}
    for node in all_nodes:
        doc_id = node.metadata["kiln_doc_id"]
        if doc_id not in nodes_by_doc:
            nodes_by_doc[doc_id] = []
        nodes_by_doc[doc_id].append(node)

    # Check that we have nodes from all three documents
    expected_doc_ids = {
        str(doc1.document.id),
        str(doc2.document.id),
        str(doc3.document.id),
    }
    assert set(nodes_by_doc.keys()) == expected_doc_ids

    # Check chunk counts
    assert len(nodes_by_doc[str(doc1.document.id)]) == 2
    assert len(nodes_by_doc[str(doc2.document.id)]) == 3
    assert len(nodes_by_doc[str(doc3.document.id)]) == 1


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_filters_by_extractor_config_id(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_llama_index_nodes filters by extractor_config_id."""
    rag_config = rag_config_factory(extractor_config_id="target_extractor")
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create documents with different extractor config IDs
    matching_doc = mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Matching doc",
        extractor_config_id="target_extractor",
    )
    mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Non-matching doc",
        extractor_config_id="other_extractor",
    )

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    assert len(all_nodes) == 2  # Only the matching document's chunks
    for node in all_nodes:
        assert node.metadata["kiln_doc_id"] == str(matching_doc.document.id)


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_filters_by_chunker_config_id(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_llama_index_nodes filters by chunker_config_id."""
    rag_config = rag_config_factory(chunker_config_id="target_chunker")
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create documents with different chunker config IDs
    matching_doc = mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Matching doc",
        chunker_config_id="target_chunker",
    )
    mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Non-matching doc",
        chunker_config_id="other_chunker",
    )

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    assert len(all_nodes) == 2  # Only the matching document's chunks
    for node in all_nodes:
        assert node.metadata["kiln_doc_id"] == str(matching_doc.document.id)


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_filters_by_embedding_config_id(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_llama_index_nodes filters by embedding_config_id."""
    rag_config = rag_config_factory(embedding_config_id="target_embedding")
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create documents with different embedding config IDs
    matching_doc = mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Matching doc",
        embedding_config_id="target_embedding",
    )
    mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Non-matching doc",
        embedding_config_id="other_embedding",
    )

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    assert len(all_nodes) == 2  # Only the matching document's chunks
    for node in all_nodes:
        assert node.metadata["kiln_doc_id"] == str(matching_doc.document.id)


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_filters_by_all_config_ids(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_llama_index_nodes filters by all config IDs simultaneously."""
    rag_config = rag_config_factory(
        extractor_config_id="target_extractor",
        chunker_config_id="target_chunker",
        embedding_config_id="target_embedding",
    )
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create documents with different combinations of config IDs
    fully_matching_doc = mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Fully matching doc",
        extractor_config_id="target_extractor",
        chunker_config_id="target_chunker",
        embedding_config_id="target_embedding",
    )
    mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Partially matching doc",
        extractor_config_id="target_extractor",
        chunker_config_id="other_chunker",  # Different chunker
        embedding_config_id="target_embedding",
    )
    mock_chunks_factory(
        mock_project,
        rag_config,
        num_chunks=2,
        text="Non-matching doc",
        extractor_config_id="other_extractor",
        chunker_config_id="other_chunker",
        embedding_config_id="other_embedding",
    )

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    assert len(all_nodes) == 2  # Only the fully matching document's chunks
    for node in all_nodes:
        assert node.metadata["kiln_doc_id"] == str(fully_matching_doc.document.id)


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_empty_project(mock_project, rag_config_factory):
    """Test iter_llama_index_nodes with an empty project."""
    rag_config = rag_config_factory()
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    assert len(all_nodes) == 0


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_batch_size(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_llama_index_nodes respects batch_size parameter."""
    rag_config = rag_config_factory()
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create a document with many chunks
    mock_chunks_factory(mock_project, rag_config, num_chunks=5, text="Test content")

    # Test with small batch size
    batch_size = 2
    batches = []
    async for batch in loader.iter_llama_index_nodes(batch_size=batch_size):
        batches.append(batch)
        assert len(batch) <= batch_size

    # Should have 3 batches: [2, 2, 1] chunks
    assert len(batches) == 3
    assert len(batches[0]) == 2
    assert len(batches[1]) == 2
    assert len(batches[2]) == 1


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_chunk_text_embedding_mismatch(
    mock_project, mock_chunks_factory, rag_config_factory, mock_attachment_factory
):
    """Test that iter_llama_index_nodes raises error on chunk text/embedding count mismatch."""
    rag_config = rag_config_factory()
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create a document with mismatched chunk text and embeddings
    doc = Document(
        id=f"doc_{uuid.uuid4()}",
        name="Test Document",
        description="Test Document",
        original_file=FileInfo(
            filename="test.pdf",
            size=100,
            mime_type="application/pdf",
            attachment=mock_attachment_factory(KilnMimeType.PDF),
        ),
        kind=Kind.DOCUMENT,
        parent=mock_project,
    )
    doc.save_to_file()

    extraction = Extraction(
        source=ExtractionSource.PROCESSED,
        extractor_config_id=rag_config.extractor_config_id,
        output=mock_attachment_factory(KilnMimeType.PDF),
        parent=doc,
    )
    extraction.save_to_file()

    # Create 2 chunks but only 1 embedding
    chunks = [
        Chunk(content=mock_attachment_factory(KilnMimeType.TXT, text=f"chunk-{i}"))
        for i in range(2)
    ]
    chunked_document = ChunkedDocument(
        chunks=chunks,
        chunker_config_id=rag_config.chunker_config_id,
        parent=extraction,
    )
    chunked_document.save_to_file()

    # Only 1 embedding for 2 chunks
    chunked_embeddings = ChunkEmbeddings(
        embeddings=[Embedding(vector=[0.1, 0.2, 0.3])],  # Only 1 embedding
        embedding_config_id=rag_config.embedding_config_id,
        parent=chunked_document,
    )
    chunked_embeddings.save_to_file()

    # Test that it raises an error
    with pytest.raises(ValueError, match="Chunk text/embedding count mismatch"):
        async for batch in loader.iter_llama_index_nodes():
            pass


@pytest.mark.asyncio
async def test_iter_llama_index_nodes_multiple_extractions_per_document(
    mock_project, mock_chunks_factory, rag_config_factory, mock_attachment_factory
):
    """Test iter_llama_index_nodes with multiple extractions per document."""
    rag_config = rag_config_factory()
    loader = VectorStoreLoader(project=mock_project, rag_config=rag_config)

    # Create a document
    doc = Document(
        id=f"doc_{uuid.uuid4()}",
        name="Test Document",
        description="Test Document",
        original_file=FileInfo(
            filename="test.pdf",
            size=100,
            mime_type="application/pdf",
            attachment=mock_attachment_factory(KilnMimeType.PDF),
        ),
        kind=Kind.DOCUMENT,
        parent=mock_project,
    )
    doc.save_to_file()

    # Create multiple extractions for the same document
    extraction1 = Extraction(
        source=ExtractionSource.PROCESSED,
        extractor_config_id=rag_config.extractor_config_id,
        output=mock_attachment_factory(KilnMimeType.PDF),
        parent=doc,
    )
    extraction1.save_to_file()

    extraction2 = Extraction(
        source=ExtractionSource.PROCESSED,
        extractor_config_id="other_extractor",  # Different extractor
        output=mock_attachment_factory(KilnMimeType.PDF),
        parent=doc,
    )
    extraction2.save_to_file()

    # Create chunked documents and embeddings for each extraction
    chunks1 = [
        Chunk(content=mock_attachment_factory(KilnMimeType.TXT, text=f"chunk1-{i}"))
        for i in range(2)
    ]
    chunked_doc1 = ChunkedDocument(
        chunks=chunks1,
        chunker_config_id=rag_config.chunker_config_id,
        parent=extraction1,
    )
    chunked_doc1.save_to_file()

    chunks2 = [
        Chunk(content=mock_attachment_factory(KilnMimeType.TXT, text=f"chunk2-{i}"))
        for i in range(3)
    ]
    chunked_doc2 = ChunkedDocument(
        chunks=chunks2,
        chunker_config_id=rag_config.chunker_config_id,
        parent=extraction2,
    )
    chunked_doc2.save_to_file()

    # Create embeddings for each chunked document
    embeddings1 = ChunkEmbeddings(
        embeddings=[Embedding(vector=[0.1, 0.2, 0.3]) for _ in range(2)],
        embedding_config_id=rag_config.embedding_config_id,
        parent=chunked_doc1,
    )
    embeddings1.save_to_file()

    embeddings2 = ChunkEmbeddings(
        embeddings=[Embedding(vector=[0.4, 0.5, 0.6]) for _ in range(3)],
        embedding_config_id=rag_config.embedding_config_id,
        parent=chunked_doc2,
    )
    embeddings2.save_to_file()

    # Test iterating through nodes
    all_nodes = []
    async for batch in loader.iter_llama_index_nodes():
        all_nodes.extend(batch)

    # Should only return nodes from the first extraction since the second has a different extractor_config_id
    assert len(all_nodes) == 2
    for node in all_nodes:
        assert node.metadata["kiln_doc_id"] == str(doc.id)
        # All nodes should have chunk indices 0 and 1 (from the first extraction)
        assert node.metadata["kiln_chunk_idx"] in [0, 1]
