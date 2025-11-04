from unittest.mock import patch

import pytest

from kiln_ai.adapters.vector_store.lancedb_helpers import (
    convert_to_llama_index_node,
    deterministic_chunk_id,
    lancedb_construct_from_config,
    store_type_to_lancedb_query_type,
)
from kiln_ai.datamodel.vector_store import (
    LanceDBConfigFTSProperties,
    LanceDBConfigHybridProperties,
    LanceDBConfigVectorProperties,
    VectorStoreConfig,
    VectorStoreType,
)
from kiln_ai.utils.uuid import string_to_uuid


class _FakeLanceDBVectorStore:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _base_properties(
    store_type: VectorStoreType, nprobes: int
) -> (
    LanceDBConfigFTSProperties
    | LanceDBConfigVectorProperties
    | LanceDBConfigHybridProperties
):
    match store_type:
        case VectorStoreType.LANCE_DB_FTS:
            return LanceDBConfigFTSProperties(
                store_type=store_type,
                similarity_top_k=5,
                overfetch_factor=2,
                vector_column_name="vec",
                text_key="text",
                doc_id_key="doc_id",
            )
        case VectorStoreType.LANCE_DB_VECTOR:
            return LanceDBConfigVectorProperties(
                store_type=store_type,
                similarity_top_k=5,
                overfetch_factor=2,
                vector_column_name="vec",
                text_key="text",
                doc_id_key="doc_id",
                nprobes=nprobes,
            )
        case VectorStoreType.LANCE_DB_HYBRID:
            return LanceDBConfigHybridProperties(
                store_type=store_type,
                similarity_top_k=5,
                overfetch_factor=2,
                vector_column_name="vec",
                text_key="text",
                doc_id_key="doc_id",
                nprobes=nprobes,
            )
        case _:
            raise ValueError(f"Unsupported store type: {store_type}")


def _make_config(store_type: VectorStoreType, nprobes: int) -> VectorStoreConfig:
    return VectorStoreConfig(
        name="test_store",
        description=None,
        store_type=store_type,
        properties=_base_properties(store_type, nprobes),
    )


def test_store_type_to_lancedb_query_type_mapping():
    assert store_type_to_lancedb_query_type(VectorStoreType.LANCE_DB_FTS) == "fts"
    assert store_type_to_lancedb_query_type(VectorStoreType.LANCE_DB_HYBRID) == "hybrid"
    assert store_type_to_lancedb_query_type(VectorStoreType.LANCE_DB_VECTOR) == "vector"


def test_store_type_to_lancedb_query_type_unsupported_raises():
    with pytest.raises(Exception):
        store_type_to_lancedb_query_type("unsupported")  # type: ignore[arg-type]


def test_lancedb_construct_from_config_includes_nprobes():
    with patch(
        "kiln_ai.adapters.vector_store.lancedb_helpers.LanceDBVectorStore",
        new=_FakeLanceDBVectorStore,
    ):
        cfg = _make_config(VectorStoreType.LANCE_DB_VECTOR, nprobes=7)

        result = lancedb_construct_from_config(
            vector_store_config=cfg,
            uri="memory://",
            api_key="k",
            region="r",
            table_name="t",
        )

    assert isinstance(result, _FakeLanceDBVectorStore)
    kwargs = result.kwargs

    assert kwargs["mode"] == "create"
    assert kwargs["uri"] == "memory://"
    assert kwargs["query_type"] == "vector"
    assert kwargs["overfetch_factor"] == 2
    assert kwargs["vector_column_name"] == "vec"
    assert kwargs["text_key"] == "text"
    assert kwargs["doc_id_key"] == "doc_id"
    assert kwargs["api_key"] == "k"
    assert kwargs["region"] == "r"
    assert kwargs["table_name"] == "t"
    # extra optional kwarg present when provided
    assert kwargs["nprobes"] == 7


def test_lancedb_construct_from_config_omits_nprobes_when_none():
    with patch(
        "kiln_ai.adapters.vector_store.lancedb_helpers.LanceDBVectorStore",
        new=_FakeLanceDBVectorStore,
    ):
        cfg = _make_config(VectorStoreType.LANCE_DB_FTS, nprobes=20)

        result = lancedb_construct_from_config(
            vector_store_config=cfg,
            uri="memory://",
            api_key=None,
            region=None,
            table_name=None,
        )

    assert isinstance(result, _FakeLanceDBVectorStore)
    kwargs = result.kwargs

    assert kwargs["query_type"] == "fts"
    assert "nprobes" not in kwargs


def test_convert_to_llama_index_node_builds_expected_structure():
    node = convert_to_llama_index_node(
        document_id="doc-123",
        chunk_idx=0,
        node_id="11111111-1111-5111-8111-111111111111",
        text="hello",
        vector=[0.1, 0.2],
    )

    assert node.id_ == "11111111-1111-5111-8111-111111111111"
    assert node.text == "hello"
    assert node.embedding == [0.1, 0.2]
    assert node.metadata["kiln_doc_id"] == "doc-123"
    assert node.metadata["kiln_chunk_idx"] == 0

    # relationship exists and points to the source document id
    from llama_index.core.schema import NodeRelationship, RelatedNodeInfo

    assert NodeRelationship.SOURCE in node.relationships
    related = node.relationships[NodeRelationship.SOURCE]
    assert isinstance(related, RelatedNodeInfo)
    assert related.node_id == "doc-123"
    assert related.node_type == "1"
    assert isinstance(related.metadata, dict)


def test_deterministic_chunk_id_uses_uuid_v5_namespace():
    doc_id = "doc-abc"
    idx = 3
    expected = str(string_to_uuid(f"{doc_id}::{idx}"))
    assert deterministic_chunk_id(doc_id, idx) == expected

    # call again to ensure the same value is returned
    assert deterministic_chunk_id(doc_id, idx) == expected
