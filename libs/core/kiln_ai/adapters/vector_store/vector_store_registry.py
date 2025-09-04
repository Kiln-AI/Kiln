import logging

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
)
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

logger = logging.getLogger(__name__)


async def vector_store_adapter_for_config(
    rag_config: RagConfig,
    vector_store_config: VectorStoreConfig,
) -> BaseVectorStoreAdapter:
    vector_store_config_id = vector_store_config.id
    if vector_store_config_id is None:
        raise ValueError("Vector store config ID is required")

    match vector_store_config.store_type:
        case VectorStoreType.LANCE_DB_FTS:
            return LanceDBAdapter(
                rag_config,
                vector_store_config,
            )
        case VectorStoreType.LANCE_DB_HYBRID:
            return LanceDBAdapter(
                rag_config,
                vector_store_config,
            )
        case VectorStoreType.LANCE_DB_VECTOR:
            return LanceDBAdapter(
                rag_config,
                vector_store_config,
            )
        case _:
            raise_exhaustive_enum_error(vector_store_config.store_type)
