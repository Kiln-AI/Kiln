import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from llama_index.vector_stores.lancedb.base import TableNotFoundError

from kiln_ai.adapters.vector_store.base_vector_store_adapter import KilnVectorStoreQuery
from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType


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
    with patch("kiln_ai.utils.config.Config.local_data_dir", return_value=temp_db_path):
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
    with patch("kiln_ai.utils.config.Config.local_data_dir", return_value=temp_db_path):
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
def similarity_vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.local_data_dir", return_value=temp_db_path):
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


@pytest.mark.asyncio
async def test_add_chunks_with_embeddings_and_similarity_search(
    similarity_vector_store_config, mock_chunked_documents
):
    """Test adding chunks and similarity search."""
    print("=== Testing Add Chunks and Similarity Search ===")

    # Create adapter using the registry
    adapter = await vector_store_adapter_for_config(similarity_vector_store_config)

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
async def test_fts_search(fts_vector_store_config, mock_chunked_documents):
    """Test full-text search functionality."""
    print("=== Testing Full-Text Search ===")

    adapter = await vector_store_adapter_for_config(fts_vector_store_config)

    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    all_chunks = await adapter.get_all_chunks()
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
async def test_hybrid_search(hybrid_vector_store_config, mock_chunked_documents):
    """Test hybrid search combining vector and text search."""
    print("=== Testing Hybrid Search ===")

    adapter = await vector_store_adapter_for_config(hybrid_vector_store_config)

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


@pytest.mark.asyncio
async def test_upsert_behavior(fts_vector_store_config, mock_chunked_documents):
    """Test that adding the same chunks multiple times works (upsert behavior)."""
    print("=== Testing Upsert Behavior ===")

    adapter = await vector_store_adapter_for_config(fts_vector_store_config)

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
    assert len(results2) >= len(results1)

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
async def test_count_records_empty_store(fts_vector_store_config):
    """Test counting records in an empty vector store."""

    adapter = await vector_store_adapter_for_config(fts_vector_store_config)

    # Fresh adapter should raise TableNotFoundError when table doesn't exist yet
    with pytest.raises(TableNotFoundError, match="Table vectors is not initialized"):
        await adapter.count_records()


@pytest.mark.asyncio
async def test_count_records_with_data(fts_vector_store_config, mock_chunked_documents):
    """Test counting records after adding data."""
    adapter = await vector_store_adapter_for_config(fts_vector_store_config)

    # Add chunks first to create the table
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Should now have records (8 chunks total across both documents)
    final_count = await adapter.count_records()
    assert final_count == 8


@pytest.mark.asyncio
async def test_count_records_with_table_none():
    """Test count_records when table is None."""
    from unittest.mock import Mock

    from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter

    # Create a mock vector store config
    mock_config = Mock()

    # Create a mock LanceDBVectorStore with table set to None
    mock_lancedb_store = Mock()
    mock_lancedb_store.table = None

    adapter = LanceDBAdapter(mock_config, mock_lancedb_store)

    # Should raise ValueError when table is None
    with pytest.raises(ValueError, match="Table is not initialized"):
        await adapter.count_records()


@pytest.mark.asyncio
async def test_get_all_chunks(fts_vector_store_config, mock_chunked_documents):
    """Test getting all chunks from the vector store."""
    adapter = await vector_store_adapter_for_config(fts_vector_store_config)

    # Add chunks first to create the table
    await adapter.add_chunks_with_embeddings(mock_chunked_documents)

    # Get all chunks
    all_chunks = await adapter.get_all_chunks()
    assert len(all_chunks) == 8  # 8 chunks total

    # Verify structure
    for chunk in all_chunks:
        assert chunk.document_id in ["doc_001", "doc_002"]
        assert len(chunk.chunk_text) > 0
        assert chunk.similarity is None  # get_all_chunks doesn't include similarity


def test_format_query_result_error_conditions():
    """Test error handling in format_query_result method."""
    from unittest.mock import Mock

    from llama_index.core.vector_stores.types import VectorStoreQueryResult

    from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter

    # Create adapter with minimal setup
    mock_config = Mock()
    mock_lancedb_store = Mock()
    adapter = LanceDBAdapter(mock_config, mock_lancedb_store)

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


def test_build_kwargs_for_query_validation_errors():
    """Test error handling in build_kwargs_for_query method."""
    from unittest.mock import Mock

    from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
    from kiln_ai.datamodel.vector_store import VectorStoreType

    # Mock config for FTS
    mock_config = Mock()
    mock_config.store_type = VectorStoreType.LANCE_DB_FTS
    mock_config.lancedb_properties.similarity_top_k = 10

    mock_lancedb_store = Mock()
    adapter = LanceDBAdapter(mock_config, mock_lancedb_store)

    # Test FTS search without query_string
    query = KilnVectorStoreQuery(query_string=None, query_embedding=None)
    with pytest.raises(
        ValueError, match="query_string must be provided for fts search"
    ):
        adapter.build_kwargs_for_query(query)

    # Test HYBRID search without required parameters
    mock_config.store_type = VectorStoreType.LANCE_DB_HYBRID
    adapter = LanceDBAdapter(mock_config, mock_lancedb_store)

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
    mock_config.store_type = VectorStoreType.LANCE_DB_VECTOR
    adapter = LanceDBAdapter(mock_config, mock_lancedb_store)

    query = KilnVectorStoreQuery(query_string=None, query_embedding=None)
    with pytest.raises(
        ValueError, match="query_embedding must be provided for vector search"
    ):
        adapter.build_kwargs_for_query(query)
