from typing import List, Tuple

from kiln_ai.adapters.rerankers.base_reranker import RerankDocument
from kiln_ai.adapters.vector_store.base_vector_store_adapter import SearchResult


def global_chunk_id(document_id: str, chunk_idx: int) -> str:
    return f"{document_id}::{chunk_idx}"


def split_global_chunk_id(global_chunk_id: str) -> Tuple[str, int]:
    parts = global_chunk_id.split("::")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid global chunk ID '{global_chunk_id}'. Expected exactly one "
            "'::' separator, in the format 'document_id::chunk_idx'."
        )

    document_id, chunk_idx = parts
    try:
        return document_id, int(chunk_idx)
    except ValueError:
        raise ValueError(
            f"Invalid global chunk ID '{global_chunk_id}'. The chunk index "
            f"'{chunk_idx}' is not an integer."
        ) from None


def convert_search_results_to_rerank_input(
    search_results: List[SearchResult],
) -> List[RerankDocument]:
    return [
        RerankDocument(
            id=global_chunk_id(search_result.document_id, search_result.chunk_idx),
            text=search_result.chunk_text,
        )
        for search_result in search_results
    ]
