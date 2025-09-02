import logging
from collections import defaultdict
from typing import Dict, Literal

from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig
from llama_index.vector_stores.lancedb.base import TableNotFoundError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LogMessage(BaseModel):
    level: Literal["info", "error", "warning"] = Field(
        description="The level of the log message",
    )
    message: str = Field(
        description="The message to display to the user",
    )


class RagProgress(BaseModel):
    total_document_count: int = Field(
        description="The total number of items to process",
        default=0,
    )

    total_document_completed_count: int = Field(
        description="The number of items that have been processed",
        default=0,
    )

    # Progress for indexing is tracked in terms of chunks, not documents. After the initial run
    # the only info we have is how many chunks are in the vector store, and so we need to know
    # the total number of chunks that should be indexed to know if it is completed or not.
    # So we need toset and send that through to the client once we know it (after completing chunking).
    total_chunk_count: int = Field(
        description="The number of chunks that should be indexed for the indexing to be completed.",
        default=0,
    )

    total_chunk_completed_count: int = Field(
        description="The number of chunks that have been indexed",
        default=0,
    )

    total_document_extracted_count: int = Field(
        description="The number of items that have been extracted",
        default=0,
    )

    total_document_extracted_error_count: int = Field(
        description="The number of items that have errored during extraction",
        default=0,
    )

    total_document_chunked_count: int = Field(
        description="The number of items that have been chunked",
        default=0,
    )

    total_document_chunked_error_count: int = Field(
        description="The number of items that have errored during chunking",
        default=0,
    )

    total_document_embedded_count: int = Field(
        description="The number of items that have been embedded",
        default=0,
    )

    total_document_embedded_error_count: int = Field(
        description="The number of items that have errored during embedding",
        default=0,
    )

    total_chunks_indexed_count: int = Field(
        description="The number of chunks that have been indexed",
        default=0,
    )

    total_chunks_indexed_error_count: int = Field(
        description="The number of chunks that have errored during indexing",
        default=0,
    )

    logs: list[LogMessage] | None = Field(
        description="A list of log messages to display to the user",
        default=None,
    )


async def count_records_in_vector_store(
    rag_config: RagConfig,
    vector_store_config: VectorStoreConfig,
) -> int:
    vector_store = await vector_store_adapter_for_config(
        rag_config, vector_store_config
    )

    try:
        count = await vector_store.count_records()
        return count
    except TableNotFoundError:
        return 0


async def count_records_in_vector_store_for_rag_config(
    project: Project,
    rag_config: RagConfig,
) -> int:
    vector_store_config = VectorStoreConfig.from_id_and_parent_path(
        str(rag_config.vector_store_config_id),
        project.path,
    )
    if vector_store_config is None:
        raise ValueError(f"Rag config {rag_config.id} has no vector store config")
    return await count_records_in_vector_store(rag_config, vector_store_config)


async def compute_current_progress_for_rag_configs(
    project: Project,
    rag_configs: list[RagConfig],
) -> Dict[str, RagProgress]:
    # each RAG config represents a unique path: extractor::chunker::embedding
    # different configs can share common prefixes
    # (e.g., extractor-1::chunker-2 for both extractor-1::chunker-2::embedding-3 and extractor-1::chunker-2::embedding-4)
    # we store prefix -> [rag config ids] mappings so at every step
    # we know all the configs that share the same upstream steps
    path_prefixes: dict[str, set[str]] = defaultdict(set)
    for rag_config in rag_configs:
        complete_path: list[str] = [
            str(rag_config.extractor_config_id),
            str(rag_config.chunker_config_id),
            str(rag_config.embedding_config_id),
        ]
        for i in range(len(complete_path)):
            prefix = "::".join(complete_path[: i + 1])
            path_prefixes[prefix].add(str(rag_config.id))

    rag_config_progress_map: dict[str, RagProgress] = {}
    for rag_config in rag_configs:
        rag_config_progress_map[str(rag_config.id)] = RagProgress(
            total_document_count=len(project.documents(readonly=True)),
            total_document_completed_count=0,
            total_chunk_count=0,
            total_chunk_completed_count=0,
            total_document_extracted_count=0,
            total_document_chunked_count=0,
            total_document_embedded_count=0,
            total_chunks_indexed_count=await count_records_in_vector_store_for_rag_config(
                project, rag_config
            ),
        )

    for document in project.documents(readonly=True):
        for extraction in document.extractions(readonly=True):
            # increment the extraction count for every rag config that has this extractor
            extraction_path_prefix = str(extraction.extractor_config_id)
            for matching_rag_config_id in path_prefixes[extraction_path_prefix]:
                rag_config_progress_map[
                    matching_rag_config_id
                ].total_document_extracted_count += 1

            for chunked_document in extraction.chunked_documents(readonly=True):
                # increment the chunked count for every rag config that has this extractor+chunker combo
                chunking_path_prefix = (
                    f"{extraction_path_prefix}::{chunked_document.chunker_config_id}"
                )
                for matching_rag_config_id in path_prefixes[chunking_path_prefix]:
                    rag_config_progress_map[
                        matching_rag_config_id
                    ].total_document_chunked_count += 1

                    rag_config_progress_map[
                        matching_rag_config_id
                    ].total_chunk_count += len(chunked_document.chunks)

                for embedding in chunked_document.chunk_embeddings(readonly=True):
                    # increment the embedding count for every rag config that has this extractor+chunker+embedding combo
                    embedding_path_prefix = (
                        f"{chunking_path_prefix}::{embedding.embedding_config_id}"
                    )
                    for matching_rag_config_id in path_prefixes[embedding_path_prefix]:
                        rag_config_progress_map[
                            matching_rag_config_id
                        ].total_document_embedded_count += 1

    # a document is completed only when all steps are completed, so overall progress is the same
    # as the least complete step
    for rag_config_id, rag_config_progress in rag_config_progress_map.items():
        rag_config_progress.total_document_completed_count = min(
            rag_config_progress.total_document_extracted_count,
            rag_config_progress.total_document_chunked_count,
            rag_config_progress.total_document_embedded_count,
        )

        rag_config_progress.total_chunk_completed_count = (
            rag_config_progress.total_chunks_indexed_count
        )

    return dict(rag_config_progress_map)


async def compute_current_progress_for_rag_config(
    project: Project,
    rag_config: RagConfig,
) -> RagProgress:
    config_progress = await compute_current_progress_for_rag_configs(
        project, [rag_config]
    )
    if str(rag_config.id) not in config_progress:
        raise ValueError(f"Failed to compute progress for rag config {rag_config.id}")
    return config_progress[str(rag_config.id)]
