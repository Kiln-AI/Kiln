from typing import Any, Dict, List, Literal

from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from kiln_ai.datamodel.vector_store import (
    VectorStoreConfig,
    VectorStoreType,
    raise_exhaustive_enum_error,
)
from kiln_ai.utils.uuid import string_to_uuid


def store_type_to_lancedb_query_type(
    store_type: VectorStoreType,
) -> Literal["fts", "hybrid", "vector"]:
    match store_type:
        case VectorStoreType.LANCE_DB_FTS:
            return "fts"
        case VectorStoreType.LANCE_DB_HYBRID:
            return "hybrid"
        case VectorStoreType.LANCE_DB_VECTOR:
            return "vector"
        case _:
            raise_exhaustive_enum_error(store_type)


def lancedb_construct_from_config(
    vector_store_config: VectorStoreConfig,
    uri: str,
    **extra_params: Any,
) -> LanceDBVectorStore:
    """Construct a LanceDBVectorStore from a VectorStoreConfig."""
    kwargs: Dict[str, Any] = {**extra_params}
    if (
        vector_store_config.lancedb_properties.nprobes is not None
        and "nprobes" not in kwargs
    ):
        kwargs["nprobes"] = vector_store_config.lancedb_properties.nprobes

    return LanceDBVectorStore(
        mode="create",
        uri=uri,
        query_type=store_type_to_lancedb_query_type(vector_store_config.store_type),
        overfetch_factor=vector_store_config.lancedb_properties.overfetch_factor,
        vector_column_name=vector_store_config.lancedb_properties.vector_column_name,
        text_key=vector_store_config.lancedb_properties.text_key,
        doc_id_key=vector_store_config.lancedb_properties.doc_id_key,
        **kwargs,
    )


def convert_to_llama_index_node(
    document_id: str,
    chunk_idx: int,
    node_id: str,
    text: str,
    vector: List[float],
) -> TextNode:
    return TextNode(
        id_=node_id,
        text=text,
        embedding=vector,
        metadata={
            # metadata is populated by some internal llama_index logic
            # that uses for example the source_node relationship
            "kiln_doc_id": document_id,
            "kiln_chunk_idx": chunk_idx,
            #
            # llama_index lancedb vector store automatically sets these metadata:
            # "doc_id": "UUID node_id of the Source Node relationship",
            # "document_id": "UUID node_id of the Source Node relationship",
            # "ref_doc_id": "UUID node_id of the Source Node relationship"
            #
            # llama_index file loaders set these metadata, which would be useful to also support:
            # "creation_date": "2025-09-03",
            # "file_name": "file.pdf",
            # "file_path": "/absolute/path/to/the/file.pdf",
            # "file_size": 395154,
            # "file_type": "application\/pdf",
            # "last_modified_date": "2025-09-03",
            # "page_label": "1",
        },
        relationships={
            # when using the llama_index loaders, llama_index groups Nodes under Documents
            # and relationships point to the Document (which is also a Node), which confusingly
            # enough does not map to an actual file (for a PDF, a Document is a page of the PDF)
            # the Document structure is not something that is persisted, so it is fine here
            # if we have a relationship to a node_id that does not exist in the db
            NodeRelationship.SOURCE: RelatedNodeInfo(
                node_id=document_id,
                node_type="1",
                metadata={},
            ),
        },
    )


def deterministic_chunk_id(document_id: str, chunk_idx: int) -> str:
    # the id_ of the Node must be a UUID string, otherwise llama_index / LanceDB fails downstream
    return str(string_to_uuid(f"{document_id}::{chunk_idx}"))
