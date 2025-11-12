import logging
from typing import Dict

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
)
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.lock import AsyncLockManager

logger = logging.getLogger(__name__)


# we cache the adapters because LanceDB requires state to persist between queries
# or it does some heavy ops, like recreating the FTS index once after instantiation
_adapter_cache: Dict[str, BaseVectorStoreAdapter] = {}
_creation_locks = AsyncLockManager()


async def vector_store_adapter_for_config(
    rag_config: RagConfig,
    vector_store_config: VectorStoreConfig,
) -> BaseVectorStoreAdapter:
    vector_store_config_id = vector_store_config.id
    if vector_store_config_id is None:
        raise ValueError("Vector store config ID is required")
    if rag_config.id is None:
        raise ValueError("Rag config ID is required")

    cache_key = f"{rag_config.id}::{vector_store_config_id}"

    async with _creation_locks.acquire(cache_key):
        cached = _adapter_cache.get(cache_key)
        if cached is not None:
            return cached

        match vector_store_config.store_type:
            case (
                VectorStoreType.LANCE_DB_FTS
                | VectorStoreType.LANCE_DB_HYBRID
                | VectorStoreType.LANCE_DB_VECTOR
            ):
                adapter = LanceDBAdapter(
                    rag_config,
                    vector_store_config,
                )

                # this flag is initially set to False in llama_index lancedb driver, it is used internally to lazy create the
                # FTS index on query (hybrid or FTS), turning it on here means that:
                # 1. An incoming query won't trigger reindexing
                # 2. A write / add node will still create reindexing
                #
                # FTS reindexing is asynchronous and can take a while, and while it rebuilds, the previous index
                # is deleted, so results are missing from the Top K, and that causes poorer results as well as unstable
                # rankings, because a few minutes later, once indexing has completed, the FTS results will start changing
                adapter.lancedb_vector_store._fts_index_ready = True
            case _:
                raise_exhaustive_enum_error(vector_store_config.store_type)

        _adapter_cache[cache_key] = adapter
        return adapter
