import logging

import lancedb
from qdrant_client import AsyncQdrantClient

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    VectorStoreConfig,
)
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.adapters.vector_store.qdrant_adapter import QdrantAdapter
from kiln_ai.datamodel.vector_store import VectorStoreType
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)


async def connect_lancedb() -> lancedb.AsyncConnection:
    try:
        return await lancedb.connect_async(
            Config.shared().local_data_dir() / "lancedb",
        )
    except Exception as e:
        raise RuntimeError(f"Error connecting to LanceDB: {e}")


async def connect_qdrant() -> AsyncQdrantClient:
    try:
        return AsyncQdrantClient(path=str(Config.shared().local_data_dir() / "qdrant"))
    except Exception as e:
        raise RuntimeError(f"Error connecting to Qdrant: {e}")


async def vector_store_adapter_for_config(
    vector_store_config: VectorStoreConfig,
) -> BaseVectorStoreAdapter:
    match vector_store_config.store_type:
        case VectorStoreType.LANCE_DB:
            connection = await connect_lancedb()
            return LanceDBAdapter(vector_store_config, connection)
        case VectorStoreType.QDRANT:
            client = await connect_qdrant()
            return QdrantAdapter(vector_store_config, client)
        case _:
            raise ValueError(f"Unsupported vector store adapter: {vector_store_config}")
