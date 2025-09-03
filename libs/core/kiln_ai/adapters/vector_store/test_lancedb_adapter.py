import os
import tempfile
import uuid
from pathlib import Path
from typing import Callable, List
from unittest.mock import patch

import pytest
from llama_index.core.schema import MetadataMode, NodeRelationship
from llama_index.core.vector_stores.types import VectorStoreQueryResult
from llama_index.vector_stores.lancedb.base import TableNotFoundError

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    KilnVectorStoreQuery,
    SearchResult,
)
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType


def get_all_nodes(adapter: LanceDBAdapter) -> List[SearchResult]:
    nodes = adapter.lancedb_vector_store.get_nodes()
    return [
        SearchResult(
            document_id=node.metadata["kiln_doc_id"],
            chunk_idx=node.metadata["kiln_chunk_idx"],
            chunk_text=node.get_content(MetadataMode.NONE),
            similarity=None,
        )
        for node in nodes
    ]


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
def hybrid_vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        yield VectorStoreConfig(
            name="test_config",
            store_type=VectorStoreType.LANCE_DB_HYBRID,
            properties={
                "similarity_top_k": 10,
                "nprobes": 10,
                "overfetch_factor": 10,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
            },
        )


@pytest.fixture
def fts_vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        yield VectorStoreConfig(
            name="test_config",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties={
                "similarity_top_k": 10,
                "overfetch_factor": 10,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
            },
        )


@pytest.fixture
def knn_vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        yield VectorStoreConfig(
            name="test_config",
            store_type=VectorStoreType.LANCE_DB_VECTOR,
            properties={
                "similarity_top_k": 10,
                "nprobes": 10,
                "overfetch_factor": 10,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
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
def create_rag_config_factory() -> Callable[
    [VectorStoreConfig, EmbeddingConfig], RagConfig
]:
    def create_rag_config(
        vector_store_config: VectorStoreConfig, embedding_config: EmbeddingConfig
    ) -> RagConfig:
        return RagConfig(
            name="test_rag",
            extractor_config_id="test_extractor",
            chunker_config_id="test_chunker",
            embedding_config_id=embedding_config.id,
            vector_store_config_id=vector_store_config.id,
        )

    return create_rag_config


def lancedb_adapter_tmp_factory(
    rag_config: RagConfig, vector_store_config: VectorStoreConfig, temp_db_path
) -> LanceDBAdapter:
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        return LanceDBAdapter(rag_config, vector_store_config)


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


@pytest.mark.asyncio
async def test_add_chunks_with_embeddings_and_similarity_search(
    knn_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
):
    """Test adding chunks and similarity search."""
    print("=== Testing Add Chunks and Similarity Search ===")

    rag_config = create_rag_config_factory(knn_vector_store_config, embedding_config)

    # Create adapter using the registry
    adapter = await vector_store_adapter_for_config(rag_config, knn_vector_store_config)

    # Add chunks to the vector store
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    print("Chunks added successfully!")

    # Test similarity search - search for a vector close to [55.0, 55.0] (NYC area chunk)
    query_vector = [55.0, 55.0]
    print(f"Searching for similar vectors to {query_vector}")

    results = await adapter.search(KilnVectorStoreQuery(query_embedding=query_vector))
    print(f"Similarity search returned {len(results)} results:")

    for i, result in enumerate(results):
        print(f"  {i + 1}. Document ID: {result.document_id}")
        print(f"     Similarity: {result.similarity}")
        print(f"     Text: {result.chunk_text}")
        print()

    # The closest should be NYC area chunk with vector [55.0, 55.0]
    assert len(results) > 0
    assert "New York City" in results[0].chunk_text
    assert "783.8 square kilometers" in results[0].chunk_text


@pytest.mark.asyncio
async def test_fts_search(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
):
    """Test full-text search functionality."""
    print("=== Testing Full-Text Search ===")
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = await vector_store_adapter_for_config(rag_config, fts_vector_store_config)

    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    assert isinstance(adapter, LanceDBAdapter)
    all_chunks = get_all_nodes(adapter)
    print(f"All chunks: {[chunk.chunk_text for chunk in all_chunks]}")

    # Test FTS search for "London"
    query_text = "london"
    print(f"Searching for text containing: '{query_text}'")

    results = await adapter.search(KilnVectorStoreQuery(query_string=query_text))
    print(f"FTS search returned {len(results)} results:")

    for i, result in enumerate(results):
        print(f"  {i + 1}. Document ID: {result.document_id}")
        print(f"     Similarity: {result.similarity}")
        print(f"     Text: {result.chunk_text}")
        print()

    # Should find both London chunks
    assert len(results) >= 2
    london_texts = [result.chunk_text for result in results]
    assert any("London, UK has a population" in text for text in london_texts)
    assert any("The area of London, UK" in text for text in london_texts)


@pytest.mark.asyncio
async def test_hybrid_search(
    hybrid_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
):
    """Test hybrid search combining vector and text search."""
    print("=== Testing Hybrid Search ===")

    rag_config = create_rag_config_factory(hybrid_vector_store_config, embedding_config)

    adapter = await vector_store_adapter_for_config(
        rag_config, hybrid_vector_store_config
    )

    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Test hybrid search - combine text "Tokyo" with vector close to Tokyo population vector [1.1, 1.2]
    query_text = "Tokyo"
    query_vector = [1.1, 1.2]
    print(f"Hybrid search for text: '{query_text}' and vector: {query_vector}")

    results = await adapter.search(
        KilnVectorStoreQuery(query_string=query_text, query_embedding=query_vector)
    )
    print(f"Hybrid search returned {len(results)} results:")

    for i, result in enumerate(results):
        print(f"  {i + 1}. Document ID: {result.document_id}")
        print(f"     Similarity: {result.similarity}")
        print(f"     Text: {result.chunk_text}")
        print()

    # Should find Tokyo-related chunks, with population chunk being highly ranked
    assert len(results) > 0
    tokyo_results = [result for result in results if "Tokyo" in result.chunk_text]
    assert len(tokyo_results) >= 2  # Both Tokyo chunks should be found


async def test_upsert_behavior(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
):
    """Test that adding the same chunks multiple times works (upsert behavior)."""
    print("=== Testing Upsert Behavior ===")

    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = await vector_store_adapter_for_config(rag_config, fts_vector_store_config)

    # Extract first document only
    first_doc = [mock_chunked_documents[0]]

    print("Adding first document...")
    await adapter.add_chunks_with_embeddings(first_doc)

    # Search to verify it's there
    results1 = await adapter.search(KilnVectorStoreQuery(query_string="Tokyo"))
    print(f"After first add: {len(results1)} Tokyo results")

    # Add the same document again
    print("Adding same document again...")
    await adapter.add_chunks_with_embeddings(first_doc)

    # Search again - should still find the same chunks (not duplicated)
    results2 = await adapter.search(KilnVectorStoreQuery(query_string="Tokyo"))
    print(f"After second add: {len(results2)} Tokyo results")

    # Print all results to see what we got
    for i, result in enumerate(results2):
        print(f"  {i + 1}. Document ID: {result.document_id}")
        print(f"     Text: {result.chunk_text}")
        print()

    # Should find Tokyo chunks but behavior may vary based on LanceDB implementation
    assert len(results2) == len(results1)

    # Add all documents
    print("Adding all documents...")
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Final search
    results3 = await adapter.search(KilnVectorStoreQuery(query_string="population"))
    print(f"After adding all documents: {len(results3)} population results")

    for i, result in enumerate(results3):
        print(f"  {i + 1}. Document ID: {result.document_id}")
        print(f"     Text: {result.chunk_text}")
        print()

    assert len(results3) > 0


@pytest.mark.asyncio
async def test_count_records_empty_store(
    fts_vector_store_config, embedding_config, create_rag_config_factory
):
    """Test counting records in an empty vector store."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = await vector_store_adapter_for_config(rag_config, fts_vector_store_config)

    # Fresh adapter should raise TableNotFoundError when table doesn't exist yet
    with pytest.raises(TableNotFoundError, match="Table vectors is not initialized"):
        await adapter.count_records()


@pytest.mark.asyncio
async def test_count_records_with_data(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
):
    """Test counting records after adding data."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = await vector_store_adapter_for_config(rag_config, fts_vector_store_config)

    # Add chunks first to create the table
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Should now have records (8 chunks total across both documents)
    final_count = await adapter.count_records()
    assert final_count == 8


@pytest.mark.asyncio
async def test_count_records_with_table_none(
    fts_vector_store_config,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test count_records when table is None."""

    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    # Create a mock vector store config
    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Should raise TableNotFoundError when table is None
    with pytest.raises(
        TableNotFoundError,
        match="Table vectors is not initialized. Please create it or add some data first.",
    ):
        await adapter.count_records()


@pytest.mark.asyncio
async def test_get_all_chunks(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test getting all chunks from the vector store."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Add chunks first to create the table
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Get all chunks
    all_chunks = get_all_nodes(adapter)
    assert len(all_chunks) == 8  # 8 chunks total

    # Verify structure
    for chunk in all_chunks:
        assert chunk.document_id in ["doc_001", "doc_002"]
        assert len(chunk.chunk_text) > 0
        assert chunk.similarity is None  # get_all_chunks doesn't include similarity


def test_format_query_result_error_conditions(
    fts_vector_store_config, embedding_config, create_rag_config_factory, temp_db_path
):
    """Test error handling in format_query_result method."""

    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    # Create adapter with minimal setup
    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Test with None ids
    query_result = VectorStoreQueryResult(ids=None, nodes=[], similarities=[])
    with pytest.raises(
        ValueError, match="ids, nodes, and similarities must not be None"
    ):
        adapter.format_query_result(query_result)

    # Test with None nodes
    query_result = VectorStoreQueryResult(ids=[], nodes=None, similarities=[])
    with pytest.raises(
        ValueError, match="ids, nodes, and similarities must not be None"
    ):
        adapter.format_query_result(query_result)

    # Test with None similarities
    query_result = VectorStoreQueryResult(ids=[], nodes=[], similarities=None)
    with pytest.raises(
        ValueError, match="ids, nodes, and similarities must not be None"
    ):
        adapter.format_query_result(query_result)

    # Test with mismatched lengths
    query_result = VectorStoreQueryResult(ids=["1", "2"], nodes=[], similarities=[])
    with pytest.raises(
        ValueError, match="ids, nodes, and similarities must have the same length"
    ):
        adapter.format_query_result(query_result)


def test_build_kwargs_for_query_validation_errors(
    create_rag_config_factory,
    hybrid_vector_store_config,
    fts_vector_store_config,
    knn_vector_store_config,
    embedding_config,
    temp_db_path,
):
    """Test error handling in build_kwargs_for_query method."""

    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Test FTS search without query_string
    query = KilnVectorStoreQuery(query_string=None, query_embedding=None)
    with pytest.raises(
        ValueError, match="query_string must be provided for fts search"
    ):
        adapter.build_kwargs_for_query(query)

    # Test HYBRID search without required parameters
    adapter = lancedb_adapter_tmp_factory(
        rag_config, hybrid_vector_store_config, temp_db_path
    )

    query = KilnVectorStoreQuery(query_string=None, query_embedding=[1.0, 2.0])
    with pytest.raises(
        ValueError,
        match="query_string and query_embedding must be provided for hybrid search",
    ):
        adapter.build_kwargs_for_query(query)

    query = KilnVectorStoreQuery(query_string="test", query_embedding=None)
    with pytest.raises(
        ValueError,
        match="query_string and query_embedding must be provided for hybrid search",
    ):
        adapter.build_kwargs_for_query(query)

    # Test VECTOR search without embedding
    adapter = lancedb_adapter_tmp_factory(
        rag_config, knn_vector_store_config, temp_db_path
    )

    query = KilnVectorStoreQuery(query_string=None, query_embedding=None)
    with pytest.raises(
        ValueError, match="query_embedding must be provided for vector search"
    ):
        adapter.build_kwargs_for_query(query)


@pytest.mark.asyncio
async def test_destroy(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test the destroy method removes the database directory."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Add some data to create the database
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Verify data exists
    count = await adapter.count_records()
    assert count == 8

    # Get the database path
    db_path = LanceDBAdapter.lancedb_path_for_config(rag_config)
    assert os.path.exists(db_path)

    # Destroy the database
    await adapter.destroy()

    # Verify the database directory is gone
    assert not os.path.exists(db_path)


def test_lancedb_path_for_config(temp_db_path):
    """Test the lancedb_path_for_config static method."""
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        # Test with valid rag_config
        rag_config = RagConfig(
            name="test_rag",
            extractor_config_id="test_extractor",
            chunker_config_id="test_chunker",
            embedding_config_id="test_embedding",
            vector_store_config_id="test_vector_store",
        )

        expected_path = str(
            Path(temp_db_path) / "rag_indexes" / "lancedb" / str(rag_config.id)
        )
        actual_path = LanceDBAdapter.lancedb_path_for_config(rag_config)

        assert actual_path == expected_path

        # Test with rag_config with no ID (should raise ValueError)
        rag_config_no_id = RagConfig(
            name="test_rag",
            extractor_config_id="test_extractor",
            chunker_config_id="test_chunker",
            embedding_config_id="test_embedding",
            vector_store_config_id="test_vector_store",
        )
        rag_config_no_id.id = None

        with pytest.raises(ValueError, match="Vector store config ID is required"):
            LanceDBAdapter.lancedb_path_for_config(rag_config_no_id)


def test_query_type_property(
    temp_db_path,
    embedding_config,
    create_rag_config_factory,
):
    """Test the query_type property returns correct values for different store types."""

    # Test FTS query type
    fts_config = VectorStoreConfig(
        name="fts_test",
        store_type=VectorStoreType.LANCE_DB_FTS,
        properties={
            "similarity_top_k": 10,
            "overfetch_factor": 10,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
        },
    )
    rag_config = create_rag_config_factory(fts_config, embedding_config)

    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        adapter = LanceDBAdapter(rag_config, fts_config)
        assert adapter.query_type == "fts"

    # Test Hybrid query type
    hybrid_config = VectorStoreConfig(
        name="hybrid_test",
        store_type=VectorStoreType.LANCE_DB_HYBRID,
        properties={
            "similarity_top_k": 10,
            "nprobes": 10,
            "overfetch_factor": 10,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
        },
    )
    rag_config = create_rag_config_factory(hybrid_config, embedding_config)

    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        adapter = LanceDBAdapter(rag_config, hybrid_config)
        assert adapter.query_type == "hybrid"

    # Test Vector query type
    vector_config = VectorStoreConfig(
        name="vector_test",
        store_type=VectorStoreType.LANCE_DB_VECTOR,
        properties={
            "similarity_top_k": 10,
            "nprobes": 10,
            "overfetch_factor": 10,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
        },
    )
    rag_config = create_rag_config_factory(vector_config, embedding_config)

    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        adapter = LanceDBAdapter(rag_config, vector_config)
        assert adapter.query_type == "vector"


@pytest.mark.asyncio
async def test_adapter_reuse_preserves_data(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test that creating the same LanceDBAdapter twice doesn't destroy/empty the db."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    # Create first adapter and add data
    adapter1 = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )
    await adapter1.add_chunks_with_embeddings([mock_chunked_documents[0]])

    # Verify data exists
    count1 = await adapter1.count_records()
    assert count1 == 4

    # Create second adapter with same config
    adapter2 = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )
    await adapter2.add_chunks_with_embeddings([mock_chunked_documents[1]])

    # Verify data still exists and wasn't destroyed by second instantiation
    count2 = await adapter2.count_records()
    assert count2 == 8

    # interesting: adapter1 is no longer usable after creating adapter2
    with pytest.raises(
        Exception,
        match="lance error: Retryable commit conflict for version 4: This CreateIndex transaction was preempted by concurrent transaction Rewrite at version 4. Please retry.",
    ):
        await adapter1.search(KilnVectorStoreQuery(query_string="Tokyo"))

    # but we can query adapter2
    results2 = await adapter2.search(KilnVectorStoreQuery(query_string="Tokyo"))
    assert len(results2) > 0


@pytest.mark.asyncio
async def test_skip_existing_chunks_when_count_matches(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test that chunks already in DB are skipped when they match incoming chunks count."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Add first document
    first_doc = [mock_chunked_documents[0]]  # doc_001 with 4 chunks
    await adapter.add_chunks_with_embeddings(first_doc)

    # Verify it was added
    count_after_first = await adapter.count_records()
    assert count_after_first == 4

    # Try to add the same document again - should be skipped
    await adapter.add_chunks_with_embeddings(first_doc)

    # Count should remain the same (chunks were skipped)
    count_after_second = await adapter.count_records()
    assert count_after_second == 4

    # Verify the chunks are still there and retrievable
    results = await adapter.search(KilnVectorStoreQuery(query_string="Tokyo"))
    assert len(results) > 0
    assert "Tokyo" in results[0].chunk_text


@pytest.mark.asyncio
async def test_batching_functionality(
    fts_vector_store_config,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
    tmp_path,
):
    """Test basic batching functionality in add_chunks_with_embeddings."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Create a document with many chunks to test batching
    large_doc_data = {
        "large_doc": [
            {"vector": [i * 0.1, i * 0.2], "text": f"Chunk {i} content"}
            for i in range(15)  # 15 chunks to test batching
        ]
    }

    large_doc_records = dicts_to_indexable_docs(large_doc_data, tmp_path)

    # Track batch sizes by patching the insert method
    batch_sizes = []
    original_ainsert_nodes = adapter.index.ainsert_nodes

    async def mock_ainsert_nodes(nodes):
        batch_sizes.append(len(nodes))
        return await original_ainsert_nodes(nodes)

    # Patch the insert method to track batch sizes
    with patch.object(adapter.index, "ainsert_nodes", side_effect=mock_ainsert_nodes):
        # Add with small batch size to force batching
        await adapter.add_chunks_with_embeddings(large_doc_records, nodes_batch_size=5)

    # Verify batching behavior
    # With 15 chunks and batch_size=5, we expect 3 batches of 5 chunks each
    expected_batch_sizes = [5, 5, 5]
    assert batch_sizes == expected_batch_sizes, (
        f"Expected batch sizes {expected_batch_sizes}, got {batch_sizes}"
    )

    # Verify all chunks were added
    count = await adapter.count_records()
    assert count == 15

    # Verify we can search and find chunks
    results = await adapter.search(KilnVectorStoreQuery(query_string="Chunk"))
    assert len(results) > 0  # Should find chunks containing "Chunk"
    assert len(results) <= 15  # Should not exceed total number of chunks


@pytest.mark.asyncio
async def test_batching_functionality_with_remainder(
    fts_vector_store_config,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
    tmp_path,
):
    """Test batching functionality with a remainder (not evenly divisible)."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Create a document with 17 chunks to test batching with remainder
    large_doc_data = {
        "large_doc": [
            {"vector": [i * 0.1, i * 0.2], "text": f"Chunk {i} content"}
            for i in range(17)  # 17 chunks to test batching with remainder
        ]
    }

    large_doc_records = dicts_to_indexable_docs(large_doc_data, tmp_path)

    # Track batch sizes by patching the insert method
    batch_sizes = []
    original_ainsert_nodes = adapter.index.ainsert_nodes

    async def mock_ainsert_nodes(nodes):
        batch_sizes.append(len(nodes))
        return await original_ainsert_nodes(nodes)

    # Patch the insert method to track batch sizes
    with patch.object(adapter.index, "ainsert_nodes", side_effect=mock_ainsert_nodes):
        # Add with batch_size=7 to get 2 full batches + 1 remainder batch
        await adapter.add_chunks_with_embeddings(large_doc_records, nodes_batch_size=7)

    # Verify batching behavior
    # With 17 chunks and batch_size=7, we expect 2 batches of 7 and 1 batch of 3
    expected_batch_sizes = [7, 7, 3]
    assert batch_sizes == expected_batch_sizes, (
        f"Expected batch sizes {expected_batch_sizes}, got {batch_sizes}"
    )

    # Verify all chunks were added
    count = await adapter.count_records()
    assert count == 17


@pytest.mark.asyncio
async def test_batching_functionality_edge_cases(
    fts_vector_store_config,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
    tmp_path,
):
    """Test batching functionality edge cases (small batches, single batch)."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Test 1: Single batch (3 chunks with batch_size=10)
    small_doc_data = {
        "small_doc": [
            {"vector": [i * 0.1, i * 0.2], "text": f"Small chunk {i} content"}
            for i in range(3)
        ]
    }

    small_doc_records = dicts_to_indexable_docs(small_doc_data, tmp_path)

    # Track batch sizes by patching the insert method
    batch_sizes = []
    original_ainsert_nodes = adapter.index.ainsert_nodes

    async def mock_ainsert_nodes(nodes):
        batch_sizes.append(len(nodes))
        return await original_ainsert_nodes(nodes)

    # Test single batch scenario
    with patch.object(adapter.index, "ainsert_nodes", side_effect=mock_ainsert_nodes):
        await adapter.add_chunks_with_embeddings(small_doc_records, nodes_batch_size=10)

    # With 3 chunks and batch_size=10, we expect 1 batch of 3 chunks
    expected_batch_sizes = [3]
    assert batch_sizes == expected_batch_sizes, (
        f"Expected batch sizes {expected_batch_sizes}, got {batch_sizes}"
    )

    # Verify all chunks were added
    count = await adapter.count_records()
    assert count == 3

    # Test 2: Very small batches (batch_size=1)
    batch_sizes.clear()  # Reset for next test

    # Create new adapter for clean state
    adapter2 = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path + "_small_batches"
    )

    with patch.object(adapter2.index, "ainsert_nodes", side_effect=mock_ainsert_nodes):
        await adapter2.add_chunks_with_embeddings(small_doc_records, nodes_batch_size=1)

    # With 3 chunks and batch_size=1, we expect 3 batches of 1 chunk each
    expected_batch_sizes = [1, 1, 1]
    assert batch_sizes == expected_batch_sizes, (
        f"Expected batch sizes {expected_batch_sizes}, got {batch_sizes}"
    )


@pytest.mark.asyncio
async def test_get_nodes_by_ids_functionality(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test get_nodes_by_ids method functionality."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # before inserting data, we should simply return an empty list
    retrieved_nodes_before_any_insert = await adapter.get_nodes_by_ids(
        [str(uuid.uuid4()), str(uuid.uuid4())]
    )
    assert len(retrieved_nodes_before_any_insert) == 0

    # Add some data
    await adapter.add_chunks_with_embeddings([mock_chunked_documents[0]])  # doc_001

    # Test getting nodes by IDs - compute expected IDs
    expected_ids = [
        adapter.compute_deterministic_chunk_id("doc_001", i) for i in range(4)
    ]

    # Get nodes by IDs
    retrieved_nodes = await adapter.get_nodes_by_ids(expected_ids)

    # Should retrieve all 4 nodes
    assert len(retrieved_nodes) == 4

    # Verify node properties
    for i, node in enumerate(retrieved_nodes):
        assert node.id_ == expected_ids[i]
        assert node.metadata["kiln_doc_id"] == "doc_001"
        assert node.metadata["kiln_chunk_idx"] == i
        assert len(node.get_content()) > 0

    # Test with non-existent IDs
    fake_ids = [adapter.compute_deterministic_chunk_id("fake_doc", i) for i in range(2)]
    retrieved_fake = await adapter.get_nodes_by_ids(fake_ids)
    assert len(retrieved_fake) == 0

    # Test with empty table (no table exists yet)
    empty_adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path + "_empty"
    )
    empty_result = await empty_adapter.get_nodes_by_ids(expected_ids)
    assert len(empty_result) == 0


@pytest.mark.asyncio
async def test_delete_nodes_by_document_id(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test delete_nodes_by_document_id method."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Add both documents
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Verify both documents are there
    count_before = await adapter.count_records()
    assert count_before == 8  # 4 chunks per document

    # Delete nodes for doc_001
    await adapter.delete_nodes_by_document_id("doc_001")

    # Verify doc_001 chunks are gone
    count_after = await adapter.count_records()
    assert count_after == 4  # Only doc_002 chunks remain

    # Verify we can still find doc_002 chunks but not doc_001
    results_doc2 = await adapter.search(KilnVectorStoreQuery(query_string="area"))
    assert len(results_doc2) > 0

    # Try to search for population (which was in doc_001) - should find no results
    # LanceDB raises a Warning when no results are found, so we catch it
    try:
        results_doc1 = await adapter.search(
            KilnVectorStoreQuery(query_string="population")
        )
        assert len(results_doc1) == 0
    except Warning as w:
        # This is expected - LanceDB raises a Warning for empty results
        assert "query results are empty" in str(w)

    # Try to delete non-existent document (should not error)
    await adapter.delete_nodes_by_document_id("non_existent_doc")
    final_count = await adapter.count_records()
    assert final_count == 4  # Count unchanged


@pytest.mark.asyncio
async def test_uuid_scheme_retrieval_and_node_properties(
    fts_vector_store_config,
    mock_chunked_documents,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test UUID scheme retrieval and that inserted nodes have correct ID and ref_doc_id."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Add first document
    await adapter.add_chunks_with_embeddings([mock_chunked_documents[0]])  # doc_001

    # Test the UUID scheme: document_id::chunk_idx
    for chunk_idx in range(4):
        # Compute expected ID using the same scheme as the adapter
        expected_id = adapter.compute_deterministic_chunk_id("doc_001", chunk_idx)

        # Retrieve the specific node by ID
        retrieved_nodes = await adapter.get_nodes_by_ids([expected_id])
        assert len(retrieved_nodes) == 1

        node = retrieved_nodes[0]

        # Test that inserted nodes have the expected ID we set
        assert node.id_ == expected_id

        # Test that inserted nodes have ref_doc_id set correctly
        # The ref_doc_id should be set through the SOURCE relationship
        source_relationship = node.relationships.get(NodeRelationship.SOURCE)
        assert source_relationship is not None
        # Handle both single RelatedNodeInfo and list of RelatedNodeInfo
        if isinstance(source_relationship, list):
            assert len(source_relationship) > 0
            assert source_relationship[0].node_id == "doc_001"
        else:
            assert source_relationship.node_id == "doc_001"

        # Verify other node properties
        assert node.metadata["kiln_doc_id"] == "doc_001"
        assert node.metadata["kiln_chunk_idx"] == chunk_idx
        assert len(node.get_content()) > 0
        assert node.embedding is not None
        assert len(node.embedding) == 2  # Our test embeddings are 2D

    # Test with a different document to ensure the scheme works consistently
    await adapter.add_chunks_with_embeddings([mock_chunked_documents[1]])  # doc_002

    # Test retrieval of doc_002 chunks
    for chunk_idx in range(4):
        expected_id = adapter.compute_deterministic_chunk_id("doc_002", chunk_idx)
        retrieved_nodes = await adapter.get_nodes_by_ids([expected_id])
        assert len(retrieved_nodes) == 1

        node = retrieved_nodes[0]
        assert node.id_ == expected_id
        assert node.metadata["kiln_doc_id"] == "doc_002"
        assert node.metadata["kiln_chunk_idx"] == chunk_idx

        # Check ref_doc_id relationship
        source_relationship = node.relationships.get(NodeRelationship.SOURCE)
        assert source_relationship is not None
        # Handle both single RelatedNodeInfo and list of RelatedNodeInfo
        if isinstance(source_relationship, list):
            assert len(source_relationship) > 0
            assert source_relationship[0].node_id == "doc_002"
        else:
            assert source_relationship.node_id == "doc_002"


@pytest.mark.asyncio
async def test_deterministic_chunk_id_consistency(
    fts_vector_store_config,
    embedding_config,
    create_rag_config_factory,
    temp_db_path,
):
    """Test that the deterministic chunk ID generation is consistent."""
    rag_config = create_rag_config_factory(fts_vector_store_config, embedding_config)

    adapter = lancedb_adapter_tmp_factory(
        rag_config, fts_vector_store_config, temp_db_path
    )

    # Test that the same document_id and chunk_idx always produce the same UUID
    doc_id = "test_doc_123"
    chunk_idx = 5

    id1 = adapter.compute_deterministic_chunk_id(doc_id, chunk_idx)
    id2 = adapter.compute_deterministic_chunk_id(doc_id, chunk_idx)

    assert id1 == id2

    # Test that different inputs produce different UUIDs
    id3 = adapter.compute_deterministic_chunk_id(doc_id, chunk_idx + 1)
    id4 = adapter.compute_deterministic_chunk_id(doc_id + "_different", chunk_idx)

    assert id1 != id3
    assert id1 != id4
    assert id3 != id4

    # Verify the format is a valid UUID string
    import uuid

    try:
        uuid.UUID(id1)  # Should not raise an exception
        uuid.UUID(id3)
        uuid.UUID(id4)
    except ValueError:
        pytest.fail("Generated IDs are not valid UUIDs")
