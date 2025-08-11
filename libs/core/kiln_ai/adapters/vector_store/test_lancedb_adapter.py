import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import lancedb
import pytest
from kiln_ai.adapters.vector_store.base_vector_store_adapter import SimilarityMetric
from kiln_ai.adapters.vector_store.lancedb_adapter import (
    LanceDBAdapter,
    LanceDBCollection,
)
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import (
    LanceDBTableSchemaVersion,
    VectorStoreConfig,
    VectorStoreType,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    db_path = tempfile.mkdtemp(suffix=".lancedb")
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
            store_type=VectorStoreType.LANCE_DB,
            properties={
                "table_schema_version": LanceDBTableSchemaVersion.V1.value,
                "vector_index_type": "hnsw",
                "hnsw_m": 16,
                "hnsw_ef_construction": 100,
                "hnsw_metric": "cosine",
                "hnsw_distance_type": "cosine",
                "hnsw_num_partitions": 4,
                "hnsw_num_sub_vectors": 4,
                "hnsw_num_bits": 8,
                "hnsw_max_iterations": 50,
                "hnsw_sample_rate": 256,
            },
        )


@pytest.fixture
def embedding_config():
    """Create an embedding config for testing."""
    return EmbeddingConfig(
        name="test_embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="text-embedding-ada-002",
        dimensions=2,
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


async def build_lancedb_adapter(
    vector_store_config: VectorStoreConfig, db_path: str
) -> LanceDBAdapter:
    """Create a mock LanceDB adapter for testing."""
    connection = await lancedb.connect_async(db_path)
    return LanceDBAdapter(
        vector_store_config=vector_store_config,
        connection=connection,
    )


async def test_create_collection(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test that create_collection creates a table with the correct schema."""
    # Create the async connection
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)

    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    assert collection is not None
    assert isinstance(collection, LanceDBCollection)

    # check we can get the collection
    collection2 = await adapter.collection(rag_config)
    assert collection2 is not None
    assert isinstance(collection2, LanceDBCollection)

    # try upserting chunks
    await collection.upsert_chunks(mock_chunked_documents)

    # check they got inserted in both collections
    count1 = await collection.count_records()
    assert count1 == 8

    # this call is required, otherwise the second collection won't be up-to-date
    await collection2.optimize()

    # check they got inserted in the second collection
    count2 = await collection2.count_records()
    assert count2 == 8

    await collection.close()
    await collection2.close()


async def test_destroy_collection(vector_store_config, temp_db_path, rag_config):
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)

    await adapter.create_collection(rag_config, vector_dimensions=2)

    await adapter.destroy_collection(rag_config)

    # check the collection is gone
    with pytest.raises(Exception):
        await adapter.collection(rag_config)


@pytest.mark.asyncio
async def test_upsert_chunks_success(
    vector_store_config, temp_db_path, mock_chunked_documents, rag_config
):
    """Test that upsert_chunks stores data correctly."""
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)

    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # before any insertions
    count = await collection.count_records()
    assert count == 0

    # upsert 6 chunks using the collection adapter
    await collection.upsert_chunks([mock_chunked_documents[0]])

    # after upserting 4 chunks (only the first document)
    count = await collection.count_records()
    assert count == 4

    # upsert all the chunks (8 in total)
    await collection.upsert_chunks(mock_chunked_documents)

    # after upserting all 8 chunks - 6 are already in the table, so we should have 8 total
    count = await collection.count_records()
    assert count == 8

    # test vector search gives us the correct nearest neighbor (L2)
    results = await collection.search_vector([54, 56], 1, SimilarityMetric.L2)
    assert len(results) == 1
    assert (
        results[0]["text"]
        == "The area of New York City, USA is approximately 783.8 square kilometers"
    )

    # test FTS search gives us the correct documents
    results = await collection.search_fts("london", 10)
    assert len(results) == 2
    # check that we get back the correct documents
    for result in results:
        assert result["text"] in [
            "London, UK has a population of roughly 9 million people",
            "The area of London, UK is approximately 1,572 square kilometers",
        ]

    await collection.close()

    await adapter.destroy_collection(rag_config)


@pytest.mark.asyncio
async def test_lancedb_error_handling(vector_store_config, temp_db_path, rag_config):
    """Test error handling in the LanceDB adapter."""
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)

    # try to destroy a collection that doesn't exist
    with pytest.raises(ValueError, match="Table.*was not found"):
        await adapter.destroy_collection(rag_config)

    with pytest.raises(Exception):
        await adapter.collection(rag_config)


@pytest.mark.asyncio
async def test_lancedb_collection_edge_cases(
    vector_store_config, temp_db_path, rag_config
):
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)

    # test count_records on empty table
    count = await collection.count_records()
    assert count == 0

    # test optimize on empty table (should not fail)
    await collection.optimize()

    # test search_fts on empty table
    results = await collection.search_fts("test", 5)
    assert len(results) == 0

    # test search_vector on empty table
    results = await collection.search_vector([1.0, 1.0], 5, SimilarityMetric.L2)
    assert len(results) == 0

    # test close
    await collection.close()


@pytest.mark.asyncio
async def test_lancedb_recreate_collection(
    vector_store_config, temp_db_path, mock_chunked_documents, rag_config
):
    """Test recreating a collection with the same name."""
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)

    # Create a RAG config for testing
    rag_config = RagConfig(
        name="test_rag",
        extractor_config_id="test_extractor",
        chunker_config_id="test_chunker",
        embedding_config_id="test_embedding",
        vector_store_config_id=vector_store_config.id,
    )

    # Create collection first time
    collection1 = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Insert some data
    await collection1.upsert_chunks(mock_chunked_documents)
    count1 = await collection1.count_records()
    assert count1 > 0

    # Recreate collection (should overwrite)
    collection2 = await adapter.create_collection(rag_config, vector_dimensions=2)

    # Check that data was cleared
    count2 = await collection2.count_records()
    assert count2 == 0

    # Clean up
    await adapter.destroy_collection(rag_config)


async def test_create_collection_hnsw_index_empty_table(
    vector_store_config, temp_db_path, rag_config
):
    """Test creating a collection with an HNSW index."""
    vector_store_config.properties["vector_index_type"] = "hnsw"
    vector_store_config.properties["hnsw_m"] = 16
    vector_store_config.properties["hnsw_ef_construction"] = 100
    vector_store_config.properties["hnsw_distance_type"] = "cosine"
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)

    # HNSW needs data in the table; if the table is empty, we should do nothing and not raise an error
    await adapter.create_collection(rag_config, vector_dimensions=2)


async def test_create_collection_hnsw_index_with_data(
    vector_store_config, temp_db_path, rag_config, mock_chunked_documents
):
    """Test creating a collection with an HNSW index."""
    vector_store_config.properties["vector_index_type"] = "hnsw"
    vector_store_config.properties["hnsw_m"] = 16
    vector_store_config.properties["hnsw_ef_construction"] = 100
    vector_store_config.properties["hnsw_distance_type"] = "cosine"
    adapter = await build_lancedb_adapter(vector_store_config, temp_db_path)

    # insert some data
    collection = await adapter.create_collection(rag_config, vector_dimensions=2)
    await collection.upsert_chunks(mock_chunked_documents)

    # try a vector search
    results = await collection.search_vector([54, 56], 1, SimilarityMetric.COSINE)
    assert len(results) == 1
