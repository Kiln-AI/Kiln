import logging

import chromadb
import lancedb
import weaviate
from chromadb.api import ClientAPI
from chromadb.config import Settings

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    VectorStoreConfig,
)
from kiln_ai.adapters.vector_store.chroma_adapter import ChromaAdapter
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.adapters.vector_store.weaviate_adapter import WeaviateAdapter
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


async def connect_chroma() -> ClientAPI:
    # TODO: maybe singleton, seems like it loads the data into memory on init
    # so would not want to do that per vector store adapter instance
    # need to double check if this is stateless / collection-independent
    #
    # or maybe one folder per rag config instead, since this is the context boundary
    # users would be working with, otherwise all rag configs might get loaded into memory
    try:
        return chromadb.PersistentClient(
            path=Config.shared().local_data_dir() / "chroma",
            settings=Settings(
                # some controls over memory usage:
                # https://cookbook.chromadb.dev/strategies/memory-management/
                chroma_segment_cache_policy="LRU",
                chroma_memory_limit_bytes=10000000000,  # ~10GB
            ),
        )
    except Exception as e:
        raise RuntimeError(f"Error connecting to Chroma: {e}")


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
        case VectorStoreType.LANCE_DB:
            connection = await connect_lancedb()
            return LanceDBAdapter(vector_store_config, connection)
        case VectorStoreType.CHROMA:
            client = await connect_chroma()
            return ChromaAdapter(vector_store_config, client)
        case VectorStoreType.WEAVIATE:
            client = await connect_weaviate()
            return WeaviateAdapter(vector_store_config, client)
        case _:
            raise ValueError(f"Unsupported vector store adapter: {vector_store_config}")
