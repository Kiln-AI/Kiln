import uuid
from dataclasses import dataclass
from typing import AsyncGenerator

import pytest
from llama_index.core.schema import TextNode

from kiln_ai.adapters.vector_store_loaders.base_vector_store_loader import (
    BaseVectorStoreLoader,
)
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


class ConcreteVectorStoreLoader(BaseVectorStoreLoader):
    """Concrete implementation for testing the abstract base class."""

    async def insert_nodes(
        self,
        nodes: list[TextNode],
        flush_batch_size: int = 100,
    ) -> None:
        raise NotImplementedError("Not implemented")

    async def iter_llama_index_nodes(self) -> AsyncGenerator[TextNode, None]:
        raise NotImplementedError("Not implemented")


def test_iter_docs_with_chunks_single_document(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test iter_docs_with_chunks with a single document that matches all config IDs."""
    rag_config = rag_config_factory()
    loader = ConcreteVectorStoreLoader()

    # Create a document with chunks
    doc_with_chunks = mock_chunks_factory(
        mock_project, rag_config, num_chunks=3, text="Test content"
    )

    # Test iterating through docs with chunks
    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.document_id == str(doc_with_chunks.document.id)
    assert doc.chunked_document.id == doc_with_chunks.chunked_document.id
    assert doc.chunk_embeddings.id == doc_with_chunks.chunked_embeddings.id


def test_iter_docs_with_chunks_multiple_documents(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test iter_docs_with_chunks with multiple documents."""
    rag_config = rag_config_factory()
    loader = ConcreteVectorStoreLoader()

    # Create multiple documents
    doc1 = mock_chunks_factory(mock_project, rag_config, num_chunks=2, text="Doc 1")
    doc2 = mock_chunks_factory(mock_project, rag_config, num_chunks=3, text="Doc 2")
    doc3 = mock_chunks_factory(mock_project, rag_config, num_chunks=1, text="Doc 3")

    # Test iterating through docs with chunks
    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    assert len(docs) == 3
    doc_ids = {doc.document_id for doc in docs}
    expected_ids = {
        str(doc1.document.id),
        str(doc2.document.id),
        str(doc3.document.id),
    }
    assert doc_ids == expected_ids


def test_iter_docs_with_chunks_filters_by_extractor_config_id(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_docs_with_chunks filters by extractor_config_id."""
    rag_config = rag_config_factory(extractor_config_id="target_extractor")
    loader = ConcreteVectorStoreLoader()

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

    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    assert len(docs) == 1
    assert docs[0].document_id == str(matching_doc.document.id)


def test_iter_docs_with_chunks_filters_by_chunker_config_id(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_docs_with_chunks filters by chunker_config_id."""
    rag_config = rag_config_factory(chunker_config_id="target_chunker")
    loader = ConcreteVectorStoreLoader()

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

    # Test iterating through docs with chunks
    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    assert len(docs) == 1
    assert docs[0].document_id == str(matching_doc.document.id)


def test_iter_docs_with_chunks_filters_by_embedding_config_id(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_docs_with_chunks filters by embedding_config_id."""
    rag_config = rag_config_factory(embedding_config_id="target_embedding")
    loader = ConcreteVectorStoreLoader()

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

    # Test iterating through docs with chunks
    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    assert len(docs) == 1
    assert docs[0].document_id == str(matching_doc.document.id)


def test_iter_docs_with_chunks_filters_by_all_config_ids(
    mock_project, mock_chunks_factory, rag_config_factory
):
    """Test that iter_docs_with_chunks filters by all config IDs simultaneously."""
    rag_config = rag_config_factory(
        extractor_config_id="target_extractor",
        chunker_config_id="target_chunker",
        embedding_config_id="target_embedding",
    )
    loader = ConcreteVectorStoreLoader()

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

    # Test iterating through docs with chunks
    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    assert len(docs) == 1
    assert docs[0].document_id == str(fully_matching_doc.document.id)


def test_iter_docs_with_chunks_empty_project(mock_project, rag_config_factory):
    """Test iter_docs_with_chunks with an empty project."""
    rag_config = rag_config_factory()
    loader = ConcreteVectorStoreLoader()

    # Test iterating through docs with chunks
    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    assert len(docs) == 0


def test_iter_docs_with_chunks_multiple_extractions_per_document(
    mock_project, mock_chunks_factory, rag_config_factory, mock_attachment_factory
):
    """Test iter_docs_with_chunks with multiple extractions per document."""
    rag_config = rag_config_factory()
    loader = ConcreteVectorStoreLoader()

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

    # Test iterating through docs with chunks
    docs = list(loader.iter_docs_with_chunks(mock_project, rag_config))

    # Should only return the first extraction since the second has a different extractor_config_id
    assert len(docs) == 1
    assert docs[0].document_id == str(doc.id)
    assert docs[0].chunked_document.id == chunked_doc1.id
    assert docs[0].chunk_embeddings.id == embeddings1.id
