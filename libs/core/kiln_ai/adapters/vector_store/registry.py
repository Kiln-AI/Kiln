import logging

import weaviate

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    VectorStoreConfig,
)
from kiln_ai.adapters.vector_store.weaviate_adapter import WeaviateAdapter
from kiln_ai.datamodel.vector_store import VectorStoreType
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)


async def connect_weaviate() -> weaviate.WeaviateAsyncClient:
    try:
        # docs: https://docs.weaviate.io/deploy/installation-guides/embedded
        client = weaviate.WeaviateAsyncClient(
            embedded_options=weaviate.embedded.EmbeddedOptions(
                additional_env_vars={
                    "ENABLE_MODULES": "backup-filesystem",
                    "BACKUP_FILESYSTEM_PATH": "/tmp/backups",
                },
                persistence_data_path=str(
                    Config.shared().local_data_dir() / "weaviate"
                ),
            )
        )
        await client.connect()
        return client

    except Exception as e:
        raise RuntimeError(f"Error connecting to Weaviate: {e}")


async def vector_store_adapter_for_config(
    vector_store_config: VectorStoreConfig,
) -> BaseVectorStoreAdapter:
    match vector_store_config.store_type:
        case VectorStoreType.WEAVIATE:
            client = await connect_weaviate()
            return WeaviateAdapter(vector_store_config, client)
        case _:
            raise ValueError(f"Unsupported vector store adapter: {vector_store_config}")
