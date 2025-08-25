import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import lancedb
import pytest

from kiln_ai.adapters.vector_store.base_vector_store_adapter import VectorStoreConfig
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.adapters.vector_store.registry import (
    connect_lancedb,
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.vector_store import LanceDBTableSchemaVersion, VectorStoreType


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
                "vector_index_type": "bruteforce",
            },
        )


class TestConnectLanceDB:
    """Test the connect_lancedb function."""

    @pytest.mark.asyncio
    async def test_connect_lancedb_success(self, temp_db_path):
        """Test successful connection to LanceDB."""
        with patch("kiln_ai.utils.config.Config.shared") as mock_config:
            mock_config.return_value.local_data_dir.return_value = Path(temp_db_path)

            connection = await connect_lancedb()

            assert connection is not None
            assert isinstance(connection, lancedb.AsyncConnection)

    @pytest.mark.asyncio
    async def test_connect_lancedb_connection_error(self):
        """Test LanceDB connection error handling."""
        with patch("kiln_ai.utils.config.Config.shared") as mock_config:
            mock_config.return_value.local_data_dir.return_value = "/invalid/path"

            with pytest.raises(RuntimeError, match="Error connecting to LanceDB:"):
                await connect_lancedb()

    @pytest.mark.asyncio
    async def test_connect_lancedb_uses_config_shared(self):
        """Test that connect_lancedb uses Config.shared().local_data_dir()."""
        with patch("kiln_ai.utils.config.Config.shared") as mock_config:
            mock_config.return_value.local_data_dir.return_value = Path(
                tempfile.mkdtemp()
            )

            await connect_lancedb()

            mock_config.assert_called_once()
            mock_config.return_value.local_data_dir.assert_called_once()


class TestVectorStoreAdapterForConfig:
    """Test the vector_store_adapter_for_config function."""

    @pytest.mark.asyncio
    async def test_vector_store_adapter_for_config_lance_db(self, vector_store_config):
        """Test creating LanceDB adapter for LANCE_DB store type."""
        with patch(
            "kiln_ai.adapters.vector_store.registry.connect_lancedb"
        ) as mock_connect:
            mock_connection = AsyncMock()
            mock_connect.return_value = mock_connection

            adapter = await vector_store_adapter_for_config(vector_store_config)

            assert isinstance(adapter, LanceDBAdapter)
            assert adapter.vector_store_config == vector_store_config
            assert adapter.connection == mock_connection
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_store_adapter_for_config_unsupported_type(self):
        """Test error handling for unsupported vector store types."""
        # Create a mock config with an invalid store type
        unsupported_config = MagicMock()
        unsupported_config.store_type = "INVALID_TYPE"
        unsupported_config.name = "unsupported"

        with pytest.raises(ValueError, match="Unsupported vector store adapter"):
            await vector_store_adapter_for_config(unsupported_config)

    @pytest.mark.asyncio
    async def test_vector_store_adapter_for_config_calls_connect_lancedb(
        self, vector_store_config
    ):
        """Test that connect_lancedb is called when creating LanceDB adapter."""
        with patch(
            "kiln_ai.adapters.vector_store.registry.connect_lancedb"
        ) as mock_connect:
            mock_connection = AsyncMock()
            mock_connect.return_value = mock_connection

            await vector_store_adapter_for_config(vector_store_config)

            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_store_adapter_for_config_passes_config_to_adapter(
        self, vector_store_config
    ):
        """Test that the adapter receives the correct vector store config."""
        with patch(
            "kiln_ai.adapters.vector_store.registry.connect_lancedb"
        ) as mock_connect:
            mock_connection = AsyncMock()
            mock_connect.return_value = mock_connection

            adapter = await vector_store_adapter_for_config(vector_store_config)

            assert adapter.vector_store_config == vector_store_config
            assert adapter.vector_store_config.name == "test_config"
            assert adapter.vector_store_config.store_type == VectorStoreType.LANCE_DB
