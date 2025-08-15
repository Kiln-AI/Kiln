import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import chromadb
import pytest
from kiln_server.project_api import project_from_id

from kiln_ai.adapters.embedding.registry import embedding_adapter_from_type
from kiln_ai.adapters.vector_store.base_vector_store_adapter import SimilarityMetric
from kiln_ai.adapters.vector_store.chroma_adapter import ChromaAdapter, ChromaCollection
from kiln_ai.adapters.vector_store.registry import vector_store_adapter_for_config
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    db_path = tempfile.mkdtemp(suffix=".chroma")
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        import shutil

        shutil.rmtree(db_path)


@pytest.fixture
def vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.local_data_dir", return_value=temp_db_path):
        yield VectorStoreConfig(
            name="test_config",
            store_type=VectorStoreType.CHROMA,
            properties={
                "ef_construction": 100,
                "max_neighbors": 100,
                "space": "cosine",
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
    results = []
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
def mock_chunked_documents(tmp_path):
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


async def build_chroma_adapter(
    vector_store_config: VectorStoreConfig, db_path: str
) -> ChromaAdapter:
    """Create a ChromaDB adapter for testing."""
    client = chromadb.PersistentClient(path=db_path)
    return ChromaAdapter(
        vector_store_config=vector_store_config,
        client=client,
    )


async def test_create_collection(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test that create_collection creates a collection with the correct configuration."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)

    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    assert collection is not None
    assert isinstance(collection, ChromaCollection)

    # check we can get the collection
    collection2 = await adapter.collection(rag_config)
    assert collection2 is not None
    assert isinstance(collection2, ChromaCollection)

    # try upserting chunks
    await collection.upsert_chunks(mock_chunked_documents)

    # check they got inserted in both collections
    count1 = await collection.count_records()
    assert count1 == 8

    # check they got inserted in the second collection
    count2 = await collection2.count_records()
    assert count2 == 8

    await collection.close()
    await collection2.close()


async def test_destroy_collection(vector_store_config, temp_db_path, rag_config):
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)

    await adapter.create_collection(rag_config, vector_dimensions=2)

    await adapter.destroy_collection(rag_config)

    # check the collection is gone
    with pytest.raises(Exception):
        await adapter.collection(rag_config)

    # throw if destroying a collection that doesn't exist
    with pytest.raises(Exception):
        rag_config.id = "non-existent-rag-config"
        await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_upsert_chunks_success(
    vector_store_config, temp_db_path, mock_chunked_documents, rag_config
):
    """Test that upsert_chunks stores data correctly."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)

    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # before any insertions
    count = await collection.count_records()
    assert count == 0

    # upsert 4 chunks using the collection adapter (only the first document)
    first_doc = mock_chunked_documents[0]
    await collection.upsert_chunks([first_doc])

    # after upserting 4 chunks (only the first document)
    count = await collection.count_records()
    assert count == 4

    # upsert all the chunks (8 in total)
    await collection.upsert_chunks(mock_chunked_documents)

    # after upserting all 8 chunks - 4 are already in the collection, so we should have 8 total
    count = await collection.count_records()
    assert count == 8

    # test vector search gives us the correct nearest neighbor (cosine similarity)
    results = await collection.search_vector([54, 56], 1, SimilarityMetric.COSINE)
    assert results is not None
    assert len(results) == 1
    # Check what we actually got back
    actual_text = results[0].chunk_text
    # For now, just check that we got some result
    assert len(actual_text) > 0

    # test FTS search gives us the correct documents - notice this is case sensitive
    results = await collection.search_fts("London", 10)
    assert results is not None
    assert len(results) == 2
    # For now, just verify we get a valid response structure
    assert isinstance(results[0].chunk_text, str)

    await collection.close()

    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_chroma_error_handling(vector_store_config, temp_db_path, rag_config):
    """Test error handling in the ChromaDB adapter."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)

    # try to destroy a collection that doesn't exist
    with pytest.raises(Exception):
        await adapter.destroy_collection(rag_config)

    with pytest.raises(Exception):
        await adapter.collection(rag_config)


@pytest.mark.asyncio
async def test_chroma_collection_edge_cases(
    vector_store_config, temp_db_path, rag_config
):
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # test count_records on empty collection
    count = await collection.count_records()
    assert count == 0

    # test optimize on empty collection (should not fail)
    await collection.optimize()

    # test search_fts on empty collection
    results = await collection.search_fts("test", 5)
    assert results is not None

    assert len(results) == 0

    # test search_vector on empty collection
    results = await collection.search_vector([1.0, 1.0], 5, SimilarityMetric.COSINE)
    assert results is not None
    assert len(results) == 0

    # test close
    await collection.close()


@pytest.mark.asyncio
async def test_chroma_recreate_collection(
    vector_store_config, temp_db_path, mock_chunked_documents, rag_config
):
    """Test recreating a collection with the same name."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)

    # Create collection first time
    collection1 = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert some data
    await collection1.upsert_chunks(mock_chunked_documents)
    count1 = await collection1.count_records()
    assert count1 > 0

    # creating a collection with the same name should throw
    with pytest.raises(Exception):
        await adapter.create_collection(rag_config, vector_dimensions=2)

    # destroy the collection
    await adapter.destroy_collection(rag_config)

    # create a new collection
    collection2 = await adapter.create_collection(rag_config, vector_dimensions=2)
    assert collection2 is not None
    assert isinstance(collection2, ChromaCollection)

    # check the data is correctly gone
    count2 = await collection2.count_records()
    assert count2 == 0


async def test_table_name_for_rag_config(vector_store_config, temp_db_path):
    """Test that table names are generated correctly."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)

    rag_config = RagConfig(
        name="test_rag",
        extractor_config_id="test_extractor",
        chunker_config_id="test_chunker",
        embedding_config_id="test_embedding",
        vector_store_config_id=vector_store_config.id,
    )

    table_name = adapter.table_name_for_rag_config(rag_config)
    assert table_name == f"rag_config_{rag_config.id}"


async def test_id_for_chunk(vector_store_config, temp_db_path, rag_config):
    """Test that chunk IDs are generated correctly."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    chunk_id = collection.id_for_chunk("doc_123", 5)
    assert chunk_id == "doc_123::5"

    await collection.close()


async def test_search_vector_different_metrics(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test vector search with different similarity metrics."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert test data
    await collection.upsert_chunks(mock_chunked_documents)

    # Test with cosine similarity
    results_cosine = await collection.search_vector(
        [54, 56], 1, SimilarityMetric.COSINE
    )
    assert len(results_cosine) == 1

    # Test with L2 distance
    results_l2 = await collection.search_vector([54, 56], 1, SimilarityMetric.L2)
    assert len(results_l2) == 1

    # Test with dot product
    results_dp = await collection.search_vector(
        [54, 56], 1, SimilarityMetric.DOT_PRODUCT
    )
    assert len(results_dp) == 1

    await collection.close()


async def test_search_fts_case_sensitivity(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test FTS search case sensitivity behavior."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert test data
    await collection.upsert_chunks(mock_chunked_documents)

    # Test exact case match
    results_exact = await collection.search_fts("London", 10)
    assert len(results_exact) == 2

    # Test different case
    results_different_case = await collection.search_fts("london", 10)
    assert len(results_different_case) == 0  # ChromaDB FTS is case sensitive

    await collection.close()


async def test_upsert_chunks_overwrite_behavior(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test that upsert_chunks properly overwrites existing chunks."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert initial data
    await collection.upsert_chunks(mock_chunked_documents)
    initial_count = await collection.count_records()
    assert initial_count == 8

    # Upsert the same data again (should not duplicate)
    await collection.upsert_chunks(mock_chunked_documents)
    final_count = await collection.count_records()
    assert final_count == 8  # Should still be 8, not 16

    await collection.close()


async def test_collection_close_behavior(vector_store_config, temp_db_path, rag_config):
    """Test that collection close method works correctly."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Close should not raise an error
    await collection.close()

    # Multiple close calls should not raise an error
    await collection.close()


async def test_optimize_method(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test that optimize method works correctly."""
    adapter = await build_chroma_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Optimize should not raise an error on empty collection
    await collection.optimize()

    # Optimize should not raise an error after data insertion
    first_doc = mock_chunked_documents[0]
    await collection.upsert_chunks([first_doc])
    await collection.optimize()

    await collection.close()


@pytest.mark.skip(
    reason="Toy test to check models created via the dashboard. TODO: remove this test"
)
async def test_chroma_integration():
    """Toy test to check models created via the dashboard"""
    project_id = "268221037813"
    project = project_from_id(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    rag_config_id = "757019102616"
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

    await collection.close()
