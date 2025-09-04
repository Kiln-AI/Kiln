import os
import tempfile
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
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
def lancedb_fts_vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        config = VectorStoreConfig(
            name="test_config",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties={
                "similarity_top_k": 10,
                "overfetch_factor": 20,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
            },
        )
        # Set an ID for the config since build_lancedb_vector_store requires it
        config.id = "test_config_id"
        yield config


@pytest.fixture
def lancedb_knn_vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        config = VectorStoreConfig(
            name="test_config",
            store_type=VectorStoreType.LANCE_DB_VECTOR,
            properties={
                "similarity_top_k": 10,
                "overfetch_factor": 20,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
                "nprobes": 10,
            },
        )
        # Set an ID for the config since build_lancedb_vector_store requires it
        config.id = "test_config_id"
        yield config


@pytest.fixture
def lancedb_hybrid_vector_store_config(temp_db_path):
    """Create a vector store config for testing."""
    with patch("kiln_ai.utils.config.Config.settings_dir", return_value=temp_db_path):
        config = VectorStoreConfig(
            name="test_config",
            store_type=VectorStoreType.LANCE_DB_HYBRID,
            properties={
                "similarity_top_k": 10,
                "overfetch_factor": 20,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
                "nprobes": 10,
            },
        )
        # Set an ID for the config since build_lancedb_vector_store requires it
        config.id = "test_config_id"
        yield config


class TestVectorStoreAdapterForConfig:
    """Test the vector_store_adapter_for_config function."""

    @pytest.mark.asyncio
    async def test_vector_store_adapter_for_config_unsupported_type(
        self,
        create_rag_config_factory,
        lancedb_fts_vector_store_config,
        embedding_config,
    ):
        """Test error handling for unsupported vector store types."""
        # Create a mock config with an invalid store type
        unsupported_config = MagicMock()
        unsupported_config.store_type = "INVALID_TYPE"
        unsupported_config.name = "unsupported"
        unsupported_config.id = "test_config_id"

        rag_config = create_rag_config_factory(
            MagicMock(spec=VectorStoreConfig, id="test_config_id"), embedding_config
        )
        with pytest.raises(ValueError, match="Unhandled enum value"):
            await vector_store_adapter_for_config(rag_config, unsupported_config)

    async def test_lancedb_fts_vector_store_adapter_for_config(
        self,
        lancedb_fts_vector_store_config,
        create_rag_config_factory,
        embedding_config,
    ):
        rag_config = create_rag_config_factory(
            lancedb_fts_vector_store_config, embedding_config
        )
        adapter = await vector_store_adapter_for_config(
            rag_config, lancedb_fts_vector_store_config
        )

        assert adapter.vector_store_config == lancedb_fts_vector_store_config
        assert adapter.vector_store_config.name == "test_config"
        assert adapter.vector_store_config.store_type == VectorStoreType.LANCE_DB_FTS

    async def test_lancedb_hybrid_vector_store_adapter_for_config(
        self,
        lancedb_hybrid_vector_store_config,
        create_rag_config_factory,
        embedding_config,
    ):
        rag_config = create_rag_config_factory(
            lancedb_hybrid_vector_store_config, embedding_config
        )
        adapter = await vector_store_adapter_for_config(
            rag_config, lancedb_hybrid_vector_store_config
        )

        assert adapter.vector_store_config == lancedb_hybrid_vector_store_config
        assert adapter.vector_store_config.name == "test_config"
        assert adapter.vector_store_config.store_type == VectorStoreType.LANCE_DB_HYBRID

    async def test_lancedb_vector_vector_store_adapter_for_config(
        self,
        lancedb_knn_vector_store_config,
        create_rag_config_factory,
        embedding_config,
    ):
        rag_config = create_rag_config_factory(
            lancedb_knn_vector_store_config, embedding_config
        )
        adapter = await vector_store_adapter_for_config(
            rag_config, lancedb_knn_vector_store_config
        )
        assert adapter.vector_store_config == lancedb_knn_vector_store_config
        assert adapter.vector_store_config.name == "test_config"
        assert adapter.vector_store_config.store_type == VectorStoreType.LANCE_DB_VECTOR
