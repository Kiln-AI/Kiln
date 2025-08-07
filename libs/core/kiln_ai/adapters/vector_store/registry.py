import logging

import lancedb
from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    VectorStoreConfig,
)
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.datamodel.vector_store import LanceDBConfigProperties, VectorStoreType

logger = logging.getLogger(__name__)


async def lancedb_connection_for_config(
    config: LanceDBConfigProperties,
) -> lancedb.AsyncConnection:
    try:
        return await lancedb.connect_async(config.path)
    except Exception as e:
        raise RuntimeError(f"Error connecting to LanceDB: {e}")


async def vector_store_adapter_for_config(
    config: VectorStoreConfig,
) -> BaseVectorStoreAdapter:
    match config.store_type:
        case VectorStoreType.LANCE_DB:
            connection = await lancedb_connection_for_config(
                config.lancedb_typed_properties()
            )
            return LanceDBAdapter(config, connection)
        case _:
            raise ValueError(f"Unsupported vector store adapter: {config}")
