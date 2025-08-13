from unittest.mock import MagicMock

import pytest

from kiln_ai.adapters.vector_store.registry import vector_store_adapter_for_config


class TestVectorStoreAdapterForConfig:
    """Test the vector_store_adapter_for_config function."""

    @pytest.mark.asyncio
    async def test_vector_store_adapter_for_config_unsupported_type(self):
        """Test error handling for unsupported vector store types."""
        # Create a mock config with an invalid store type
        unsupported_config = MagicMock()
        unsupported_config.store_type = "INVALID_TYPE"
        unsupported_config.name = "unsupported"

        with pytest.raises(ValueError, match="Unsupported vector store adapter"):
            await vector_store_adapter_for_config(unsupported_config)
