import json
import tempfile
from pathlib import Path

import pytest
from kiln_server.project_api import project_from_id
from qdrant_client import AsyncQdrantClient

from kiln_ai.adapters.embedding.registry import embedding_adapter_from_type
from kiln_ai.adapters.vector_store.base_vector_store_adapter import SimilarityMetric
from kiln_ai.adapters.vector_store.qdrant_adapter import QdrantAdapter, QdrantCollection
from kiln_ai.adapters.vector_store.registry import vector_store_adapter_for_config
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import (
    QdrantVectorIndexMetric,
    QdrantVectorIndexType,
    VectorStoreConfig,
    VectorStoreType,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    import uuid

    db_path = tempfile.mkdtemp(suffix=f".qdrant.{uuid.uuid4().hex[:8]}")
    yield db_path
    # Cleanup
    import shutil

    if Path(db_path).exists():
        shutil.rmtree(db_path)


@pytest.fixture
def vector_store_config():
    """Create a vector store config for testing."""
    return VectorStoreConfig(
        name="test_config",
        store_type=VectorStoreType.QDRANT,
        properties={
            "vector_index_type": QdrantVectorIndexType.BRUTEFORCE,
            "distance": QdrantVectorIndexMetric.COSINE,
        },
    )


@pytest.fixture
def embedding_config():
    """Create an embedding config for testing."""
    return EmbeddingConfig(
        name="test_embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="text-embedding-ada-002",
        properties={},
    )


@pytest.fixture
def rag_config(vector_store_config, embedding_config):
    return RagConfig(
        name="test_rag",
        extractor_config_id="test_extractor",
        chunker_config_id="test_chunker",
        embedding_config_id=embedding_config.id,
        vector_store_config_id=vector_store_config.id,
    )


def dicts_to_indexable_docs(
    docs: dict[str, list[dict[str, str | list[float]]]], tmp_path: Path
) -> list[tuple[str, ChunkedDocument, ChunkEmbeddings]]:
    results: list[tuple[str, ChunkedDocument, ChunkEmbeddings]] = []
    for doc_id, doc in docs.items():
        chunked_documents = ChunkedDocument(
            chunker_config_id="test_chunker",
            chunks=[],
            path=tmp_path / "chunked_document.kiln",
        )
        chunk_embeddings = ChunkEmbeddings(
            embedding_config_id="test_embedding",
            embeddings=[],
            path=tmp_path / "chunk_embeddings.kiln",
        )
        for part in doc:
            # Ensure vector is a list of floats
            vector = part["vector"]
            if isinstance(vector, list):
                vector = [float(x) for x in vector]
            else:
                vector = [float(vector)]

            chunk_embeddings.embeddings.append(Embedding(vector=vector))
            chunked_documents.chunks.append(
                Chunk(
                    content=KilnAttachmentModel.from_data(
                        str(part["text"]),
                        "text/plain",
                    )
                )
            )
        results.append((doc_id, chunked_documents, chunk_embeddings))

    return results


@pytest.fixture
def mock_chunked_documents(
    tmp_path,
) -> list[tuple[str, ChunkedDocument, ChunkEmbeddings]]:
    """Create sample chunks for testing."""
    docs: dict[str, list[dict[str, str | list[float]]]] = {
        "doc_001": [
            {
                "vector": [1.1, 1.2],
                "text": "The population of Tokyo, Japan is approximately 37 million people",
            },
            {
                "vector": [0.2, 1.8],
                "text": "New York City, USA has a population of about 8.8 million residents",
            },
            {
                "vector": [0.45452, 51.8],
                "text": "London, UK has a population of roughly 9 million people",
            },
            {
                "vector": [0.7, 0.8],
                "text": "Rio de Janeiro, Brazil has a population of about 6.7 million residents",
            },
        ],
        "doc_002": [
            {
                "vector": [50.0, 50.0],
                "text": "The area of Tokyo, Japan is approximately 2,191 square kilometers",
            },
            {
                "vector": [55.0, 55.0],
                "text": "The area of New York City, USA is approximately 783.8 square kilometers",
            },
            {
                "vector": [60.0, 60.0],
                "text": "The area of London, UK is approximately 1,572 square kilometers",
            },
            {
                "vector": [65.0, 65.0],
                "text": "The area of Rio de Janeiro, Brazil is approximately 1,256 square kilometers",
            },
        ],
    }

    return dicts_to_indexable_docs(docs, tmp_path)


def similarity_metric_to_qdrant_metric(
    similarity_metric: SimilarityMetric,
) -> QdrantVectorIndexMetric:
    """Convert SimilarityMetric to QdrantVectorIndexMetric for testing."""
    mapping = {
        SimilarityMetric.COSINE: QdrantVectorIndexMetric.COSINE,
        SimilarityMetric.L2: QdrantVectorIndexMetric.EUCLID,
        SimilarityMetric.DOT_PRODUCT: QdrantVectorIndexMetric.DOT,
    }
    return mapping[similarity_metric]


async def build_qdrant_adapter(
    vector_store_config: VectorStoreConfig, temp_db_path: str
) -> QdrantAdapter:
    """Create a Qdrant adapter for testing."""
    return QdrantAdapter(
        vector_store_config=vector_store_config,
        client=AsyncQdrantClient(path=temp_db_path),
    )


@pytest.mark.asyncio
async def test_create_collection(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test that create_collection creates a collection with the correct configuration."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)

    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    assert collection is not None
    assert isinstance(collection, QdrantCollection)

    # Check we can get the collection
    collection2 = await adapter.collection(rag_config)
    assert collection2 is not None
    assert isinstance(collection2, QdrantCollection)

    # Try upserting chunks - first doc, first 4 chunks
    await collection.upsert_chunks(mock_chunked_documents[:1])

    # Check that count_records works and returns the actual count
    count1 = await collection.count_records()
    assert count1 == 4

    # upsert the rest of the chunks (should have 4 more chunks)
    await collection.upsert_chunks(mock_chunked_documents)

    count2 = await collection.count_records()
    assert count2 == 8

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_destroy_collection(vector_store_config, temp_db_path, rag_config):
    """Test that destroy_collection works correctly."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)

    await adapter.create_collection(rag_config, vector_dimensions=2)

    await adapter.destroy_collection(rag_config)

    # Verify the collection was actually destroyed by trying to get it
    # This should raise an exception since the collection no longer exists
    with pytest.raises(Exception):
        await adapter.collection(rag_config)


@pytest.mark.asyncio
async def test_upsert_chunks_success(
    vector_store_config, temp_db_path, mock_chunked_documents, rag_config
):
    """Test that upsert_chunks stores data correctly."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)

    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Before any insertions
    count = await collection.count_records()
    assert count == 0

    # Upsert chunks using the collection adapter
    await collection.upsert_chunks(mock_chunked_documents)

    # Check that the chunks were actually inserted
    count_after = await collection.count_records()
    assert count_after == 8  # 4 chunks per document, 2 documents

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_search_fts(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test full-text search functionality."""
    # Skip this test since fastembed is not installed and FTS search requires it
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert real data first
    await collection.upsert_chunks(mock_chunked_documents)

    # Test FTS search
    results = await collection.search_fts("Tokyo", 5)

    # should find 2 results about tokyo
    assert len(results) == 2
    tokyo_result = next((r for r in results if "Tokyo" in r.chunk_text), None)
    assert tokyo_result is not None
    assert tokyo_result.document_id == "doc_001"
    assert tokyo_result.chunk_idx == 0
    assert "Tokyo" in tokyo_result.chunk_text

    # check new york
    results = await collection.search_fts("new york", 5)
    # should find 2 results about new york
    assert len(results) == 2
    new_york_result = next((r for r in results if "New York" in r.chunk_text), None)
    assert new_york_result is not None
    assert new_york_result.document_id == "doc_001"
    assert new_york_result.chunk_idx == 1
    assert "New York" in new_york_result.chunk_text

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_search_vector(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test vector search functionality."""
    vector_store_config.properties["distance"] = QdrantVectorIndexMetric.EUCLID.value
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)

    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert real data first
    await collection.upsert_chunks(mock_chunked_documents)

    # Test vector search with cosine similarity
    # Use a vector similar to doc_002 chunks which have vectors around [50.0, 50.0]
    query_vector = [54.0, 56.0]
    results = await collection.search_vector(query_vector, 3, SimilarityMetric.L2)

    # Should find results, likely from doc_002 which has similar vectors
    assert len(results) >= 1

    # check that the results are correct
    assert results[0].document_id == "doc_002"
    assert results[0].chunk_idx == 1
    assert (
        results[0].chunk_text
        == "The area of New York City, USA is approximately 783.8 square kilometers"
    )

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_search_hybrid(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test hybrid search functionality."""
    vector_store_config.properties["distance"] = QdrantVectorIndexMetric.EUCLID.value
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert real data first
    await collection.upsert_chunks(mock_chunked_documents)

    # just for the sake of testing, we use a different FTS query and vector
    # - the query is about tokyo
    # - the vector is [55.0, 55.0] which is the same as the vector about new york population
    # in reality, the vector would be the same as the query (vectorized)
    results = await collection.search_hybrid(
        "Tokyo", [55.0, 55.0], 4, SimilarityMetric.L2
    )

    # should find 2 results about tokyo (due to FTS)
    # and at least one result (matching the vector) should be about new york
    assert len(results) >= 3

    # check that two results are about tokyo and two are about new york
    tokyo_results = [r for r in results if "Tokyo" in r.chunk_text]
    assert len(tokyo_results) == 2
    new_york_results = [r for r in results if "New York" in r.chunk_text]
    assert len(new_york_results) >= 1


@pytest.mark.asyncio
async def test_search_vector_different_distance_type(
    vector_store_config, temp_db_path, rag_config
):
    """Test that search_vector raises error for mismatched distance types."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Test with different distance type
    with pytest.raises(ValueError, match="Distance type.*does not match"):
        await collection.search_vector([1.0, 1.0], 5, SimilarityMetric.L2)

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_count_records(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test count_records functionality."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Initially should have 0 records
    count_before = await collection.count_records()
    assert count_before == 0

    # Insert some data
    await collection.upsert_chunks(
        mock_chunked_documents[:1]
    )  # Just first document with 4 chunks

    count_after = await collection.count_records()
    assert count_after == 4

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_optimize_method(vector_store_config, temp_db_path, rag_config):
    """Test that optimize method raises NotImplementedError."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # should not raise an error
    await collection.optimize()

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_close_method(vector_store_config, temp_db_path, rag_config):
    """Test that close method raises NotImplementedError."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    await collection.close()

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_id_for_chunk(vector_store_config, temp_db_path, rag_config):
    """Test that chunk IDs are generated correctly."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # The id_for_chunk method uses UUID5, so we need to check that it generates
    # consistent UUIDs for the same input
    chunk_id1 = collection.id_for_chunk("doc_123", 5)
    chunk_id2 = collection.id_for_chunk("doc_123", 5)

    # Should generate the same UUID for the same input
    assert chunk_id1 == chunk_id2

    # Should generate different UUIDs for different inputs
    chunk_id3 = collection.id_for_chunk("doc_123", 6)
    assert chunk_id1 != chunk_id3

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_table_name_for_rag_config(vector_store_config, temp_db_path):
    """Test that table names are generated correctly."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)

    rag_config = RagConfig(
        name="test_rag",
        extractor_config_id="test_extractor",
        chunker_config_id="test_chunker",
        embedding_config_id="test_embedding",
        vector_store_config_id=vector_store_config.id,
    )

    table_name = adapter.table_name_for_rag_config(rag_config)
    assert table_name == f"rag_config_{rag_config.id}"


@pytest.mark.asyncio
async def test_create_collection_failure(vector_store_config, temp_db_path, rag_config):
    """Test that create_collection raises error on failure."""
    # This test would require mocking the Qdrant client to simulate failure
    # Since we're moving away from mocking, we'll test the actual error handling
    # by trying to create a collection with invalid parameters

    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)

    # Test with negative vector dimensions
    # This should fail because vector dimensions must be positive
    with pytest.raises(Exception):
        await adapter.create_collection(rag_config, vector_dimensions=-1)


@pytest.mark.asyncio
async def test_create_collection_already_exists(
    vector_store_config, temp_db_path, rag_config
):
    """Test that create_collection raises error if collection already exists."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    await adapter.create_collection(rag_config, vector_dimensions=2)

    with pytest.raises(Exception):
        await adapter.create_collection(rag_config, vector_dimensions=2)


@pytest.mark.asyncio
async def test_search_fts_empty_results(vector_store_config, temp_db_path, rag_config):
    """Test FTS search with empty results."""
    # Skip this test since fastembed is not installed and FTS search requires it
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Search in empty collection should return no results
    results = await collection.search_fts("nonexistent", 5)
    assert len(results) == 0

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_search_vector_empty_results(
    vector_store_config, temp_db_path, rag_config
):
    """Test vector search with empty results."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Search in empty collection should return no results
    results = await collection.search_vector([1.0, 1.0], 5, SimilarityMetric.COSINE)
    assert len(results) == 0

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_upsert_chunks_batch_processing(
    vector_store_config, temp_db_path, rag_config, tmp_path
):
    """Test that upsert_chunks processes batches correctly."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Create a large number of chunks to test batch processing
    large_docs = {}
    for i in range(1):  # Create 1 document with 150 chunks to test batch processing
        chunks = []
        for j in range(150):  # 150 chunks in one document
            chunks.append(
                {
                    "vector": [float(i + j * 0.1), float(i + j * 0.1 + 1)],
                    "text": f"Document {i} chunk {j} content",
                }
            )
        large_docs[f"doc_{i:03d}"] = chunks

    large_chunks = dicts_to_indexable_docs(large_docs, tmp_path)

    await collection.upsert_chunks(large_chunks)

    # Should have inserted all 150 chunks
    count = await collection.count_records()
    assert count == 150

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_collection_recreation(vector_store_config, temp_db_path, rag_config):
    """Test that collection can be recreated after destruction."""
    adapter = await build_qdrant_adapter(vector_store_config, temp_db_path)

    # Create collection first time
    collection1 = await adapter.create_collection(rag_config, vector_dimensions=2)
    assert collection1 is not None

    # Destroy the collection
    await adapter.destroy_collection(rag_config)

    # Create a new collection
    collection2 = await adapter.create_collection(rag_config, vector_dimensions=2)
    assert collection2 is not None
    assert isinstance(collection2, QdrantCollection)

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_different_distance_types(vector_store_config, rag_config):
    """Test creating collections with different distance types."""
    # Test with EUCLID distance
    euclid_config = VectorStoreConfig(
        name="test_config_euclid",
        store_type=VectorStoreType.QDRANT,
        properties={
            "vector_index_type": QdrantVectorIndexType.BRUTEFORCE,
            "distance": QdrantVectorIndexMetric.EUCLID,
        },
    )

    # Use separate temp paths to avoid locking issues
    import tempfile
    import uuid

    temp_path1 = tempfile.mkdtemp(suffix=f".qdrant.{uuid.uuid4().hex[:8]}")
    temp_path2 = tempfile.mkdtemp(suffix=f".qdrant.{uuid.uuid4().hex[:8]}")

    try:
        adapter = await build_qdrant_adapter(euclid_config, temp_path1)
        collection = await adapter.create_collection(rag_config, vector_dimensions=2)

        assert collection.distance_type == QdrantVectorIndexMetric.EUCLID

        # Cleanup
        await adapter.destroy_collection(rag_config)

        # Test with DOT distance
        dot_config = VectorStoreConfig(
            name="test_config_dot",
            store_type=VectorStoreType.QDRANT,
            properties={
                "vector_index_type": QdrantVectorIndexType.BRUTEFORCE,
                "distance": QdrantVectorIndexMetric.DOT,
            },
        )

        adapter2 = await build_qdrant_adapter(dot_config, temp_path2)
        collection2 = await adapter2.create_collection(rag_config, vector_dimensions=2)

        assert collection2.distance_type == QdrantVectorIndexMetric.DOT

        # Cleanup
        await adapter2.destroy_collection(rag_config)
    finally:
        # Clean up temp directories
        import shutil

        if Path(temp_path1).exists():
            shutil.rmtree(temp_path1)
        if Path(temp_path2).exists():
            shutil.rmtree(temp_path2)


@pytest.mark.asyncio
async def test_bruteforce_index_type(vector_store_config, temp_db_path, rag_config):
    """Test creating collections with bruteforce index type."""
    bruteforce_config = VectorStoreConfig(
        name="test_config_bruteforce",
        store_type=VectorStoreType.QDRANT,
        properties={
            "vector_index_type": QdrantVectorIndexType.BRUTEFORCE.value,
            "distance": QdrantVectorIndexMetric.COSINE.value,
        },
    )

    adapter = await build_qdrant_adapter(bruteforce_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Should be able to create collection with bruteforce index type
    assert collection is not None
    assert isinstance(collection, QdrantCollection)

    # Cleanup
    await adapter.destroy_collection(rag_config)


@pytest.mark.skip(
    reason="Toy test to check models created via the dashboard. TODO: remove this test"
)
async def test_qdrant_integration(temp_db_path):
    """Toy test to check models created via the dashboard"""
    project_id = "268221037813"
    project = project_from_id(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    rag_config_id = "230620363231"
    rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
    if not rag_config:
        raise ValueError(f"Rag config {rag_config_id} not found")

    vector_store_config = VectorStoreConfig.from_id_and_parent_path(
        str(rag_config.vector_store_config_id), project.path
    )
    if not vector_store_config:
        raise ValueError(
            f"Vector store config {rag_config.vector_store_config_id} not found"
        )

    embedding_config = EmbeddingConfig.from_id_and_parent_path(
        str(rag_config.embedding_config_id), project.path
    )
    if not embedding_config:
        raise ValueError(f"Embedding config {rag_config.embedding_config_id} not found")

    vectore_store = await vector_store_adapter_for_config(vector_store_config)

    collection = await vectore_store.collection(rag_config)

    fts_results = await collection.search_fts("parrot green", 10)
    print("======================")
    print("FTS results:")
    print(
        json.dumps([r.model_dump() for r in fts_results], indent=2, ensure_ascii=False)
    )
    print("======================")

    embedding_adapter = embedding_adapter_from_type(embedding_config)
    if not embedding_adapter:
        raise ValueError(f"Embedding adapter for {embedding_config.id} not found")

    query_embeddings = await embedding_adapter.generate_embeddings(["parrot green"])
    if not query_embeddings:
        raise ValueError(f"Query for {embedding_config.id} not found")

    query_vector = query_embeddings.embeddings[0].vector

    vec_results = await collection.search_vector(
        query_vector, 10, SimilarityMetric.COSINE
    )
    print("======================")
    print("Vector results:")
    print(
        json.dumps([r.model_dump() for r in vec_results], indent=2, ensure_ascii=False)
    )
    print("======================")

    hybrid_results = await collection.search_hybrid(
        "parrot green", query_vector, 10, SimilarityMetric.COSINE
    )
    print("======================")
    print("Hybrid results:")
    print(
        json.dumps(
            [r.model_dump() for r in hybrid_results], indent=2, ensure_ascii=False
        )
    )
    print("======================")

    await collection.close()
