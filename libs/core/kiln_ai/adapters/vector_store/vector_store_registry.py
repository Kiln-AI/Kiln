import logging
from typing import Any, Dict, Literal

from llama_index.vector_stores.lancedb import LanceDBVectorStore

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    VectorStoreConfig,
)
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.datamodel.vector_store import VectorStoreType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

logger = logging.getLogger(__name__)


def build_lancedb_vector_store(
    vector_store_config: VectorStoreConfig,
    mode: Literal["overwrite", "create"],
) -> LanceDBVectorStore:
    vector_store_config_id = vector_store_config.id
    if vector_store_config_id is None:
        raise ValueError("Vector store config ID is required")

    # kwargs is optional for fts
    kwargs: Dict[str, Any] = {}
    if vector_store_config.lancedb_properties.nprobes is not None:
        kwargs["nprobes"] = vector_store_config.lancedb_properties.nprobes

    vector_store = LanceDBVectorStore(
        uri=LanceDBAdapter.lancedb_path_for_config(vector_store_config),
        # create means it throws if the table already exists
        # overwrite means it will overwrite the entire vector store every time we add new data
        mode="create",  # FIXME: lancedb says it throws if the table already exists, but it doesn't
        query_type=LanceDBAdapter.lancedb_query_type_for_config(vector_store_config),
        overfetch_factor=vector_store_config.lancedb_properties.overfetch_factor,
        vector_column_name=vector_store_config.lancedb_properties.vector_column_name,
        text_key=vector_store_config.lancedb_properties.text_key,
        doc_id_key=vector_store_config.lancedb_properties.doc_id_key,
        **kwargs,
    )
    return vector_store


async def vector_store_adapter_for_config(
    vector_store_config: VectorStoreConfig,
    lancedb_mode: Literal["overwrite", "create"] = "overwrite",
) -> BaseVectorStoreAdapter:
    match vector_store_config.store_type:
        case VectorStoreType.LANCE_DB_FTS:
            lancedb_vector_store = build_lancedb_vector_store(
                vector_store_config, mode=lancedb_mode
            )
            return LanceDBAdapter(
                vector_store_config,
                lancedb_vector_store,
            )
        case VectorStoreType.LANCE_DB_HYBRID:
            lancedb_vector_store = build_lancedb_vector_store(
                vector_store_config, mode=lancedb_mode
            )
            return LanceDBAdapter(
                vector_store_config,
                lancedb_vector_store,
            )
        case VectorStoreType.LANCE_DB_VECTOR:
            lancedb_vector_store = build_lancedb_vector_store(
                vector_store_config, mode=lancedb_mode
            )
            return LanceDBAdapter(
                vector_store_config,
                lancedb_vector_store,
            )
        case _:
            raise_exhaustive_enum_error(vector_store_config.store_type)
