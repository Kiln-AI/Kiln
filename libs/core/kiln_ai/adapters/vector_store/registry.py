import logging

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    VectorStoreConfig,
)
from kiln_ai.adapters.vector_store.fake_adapter import FakerAdapter
from kiln_ai.datamodel.vector_store import VectorStoreType

logger = logging.getLogger(__name__)


async def vector_store_adapter_for_config(
    vector_store_config: VectorStoreConfig,
) -> BaseVectorStoreAdapter:
    match vector_store_config.store_type:
        case VectorStoreType.WEAVIATE:
            return FakerAdapter(vector_store_config)
        case _:
            raise ValueError(f"Unsupported vector store adapter: {vector_store_config}")
