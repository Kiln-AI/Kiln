from collections import defaultdict
from typing import Dict, Literal

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from pydantic import BaseModel, Field


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

    logs: list[LogMessage] | None = Field(
        description="A list of log messages to display to the user. For example, 'Extracting documents...', 'Chunking documents...', 'Saving embeddings...'",
        default=None,
    )


def compute_current_progress_for_rag_configs(
    project: Project,
    rag_configs: list[RagConfig],
) -> Dict[str, RagProgress]:
    # a rag config is a unique path through the filesystem tree
    # each config is serialized as path extractor::chunker::embedding to form path prefixes
    #
    # for example, two configs:
    # - extractor-1::chunker-2::embedding-3
    # - extractor-1::chunker-2::embedding-4
    # will share common prefixes: extractor-1 and extractor-1::chunker-2
    # we store prefix -> [rag config ids] mappings
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
            total_document_extracted_count=0,
            total_document_chunked_count=0,
            total_document_embedded_count=0,
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

                for embedding in chunked_document.chunk_embeddings(readonly=True):
                    # increment the embedding count for every rag config that has this extractor+chunker+embedding combo
                    embedding_path_prefix = (
                        f"{chunking_path_prefix}::{embedding.embedding_config_id}"
                    )
                    for matching_rag_config_id in path_prefixes[embedding_path_prefix]:
                        rag_config_progress_map[
                            matching_rag_config_id
                        ].total_document_embedded_count += 1

    # a document is completed only if all steps are completed, so the progress is the same as
    # the count of whichever step is the least complete regardless of its relative order to other steps
    for rag_config_id, rag_config_progress in rag_config_progress_map.items():
        rag_config_progress.total_document_completed_count = min(
            rag_config_progress.total_document_extracted_count,
            rag_config_progress.total_document_chunked_count,
            rag_config_progress.total_document_embedded_count,
        )

    return dict(rag_config_progress_map)


def compute_current_progress_for_rag_config(
    project: Project,
    rag_config: RagConfig,
) -> RagProgress:
    config_progress = compute_current_progress_for_rag_configs(project, [rag_config])
    if str(rag_config.id) not in config_progress:
        raise ValueError(f"Failed to compute progress for rag config {rag_config.id}")
    return config_progress[str(rag_config.id)]
