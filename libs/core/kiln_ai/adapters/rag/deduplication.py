from collections import defaultdict
from typing import DefaultDict

from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.extraction import Extraction


def deduplicate_extractions(items: list[Extraction]) -> list[Extraction]:
    grouped_items: DefaultDict[str, list[Extraction]] = defaultdict(list)
    for item in items:
        if item.extractor_config_id is None:
            raise ValueError("Extractor config ID is required")
        grouped_items[item.extractor_config_id].append(item)
    return [min(group, key=lambda x: x.created_at) for group in grouped_items.values()]


def deduplicate_chunked_documents(
    items: list[ChunkedDocument],
) -> list[ChunkedDocument]:
    grouped_items: DefaultDict[str, list[ChunkedDocument]] = defaultdict(list)
    for item in items:
        if item.chunker_config_id is None:
            raise ValueError("Chunker config ID is required")
        grouped_items[item.chunker_config_id].append(item)
    return [min(group, key=lambda x: x.created_at) for group in grouped_items.values()]


def deduplicate_chunk_embeddings(items: list[ChunkEmbeddings]) -> list[ChunkEmbeddings]:
    grouped_items: DefaultDict[str, list[ChunkEmbeddings]] = defaultdict(list)
    for item in items:
        if item.embedding_config_id is None:
            raise ValueError("Embedding config ID is required")
        grouped_items[item.embedding_config_id].append(item)
    return [min(group, key=lambda x: x.created_at) for group in grouped_items.values()]
