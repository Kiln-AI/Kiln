from kiln_ai.adapters.rag.rag_runners import (
    RagChunkingStepRunner,
    RagEmbeddingStepRunner,
    RagExtractionStepRunner,
    RagIndexingStepRunner,
    RagWorkflowRunner,
    RagWorkflowRunnerConfiguration,
)
from kiln_ai.datamodel.chunk import ChunkerConfig
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.extraction import ExtractorConfig
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig


def build_rag_workflow_runner(
    project: Project,
    rag_config_id: str,
) -> RagWorkflowRunner:
    rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
    if rag_config is None:
        raise ValueError(
            "RAG config not found",
        )

    # should not happen, but id is optional in the datamodel
    if (
        rag_config.extractor_config_id is None
        or rag_config.chunker_config_id is None
        or rag_config.embedding_config_id is None
        or rag_config.vector_store_config_id is None
    ):
        raise ValueError(
            "RAG config is missing required configs",
        )

    extractor_config = ExtractorConfig.from_id_and_parent_path(
        rag_config.extractor_config_id, project.path
    )
    if extractor_config is None:
        raise ValueError(
            "Extractor config not found",
        )

    chunker_config = ChunkerConfig.from_id_and_parent_path(
        rag_config.chunker_config_id, project.path
    )
    if chunker_config is None:
        raise ValueError(
            "Chunker config not found",
        )

    embedding_config = EmbeddingConfig.from_id_and_parent_path(
        rag_config.embedding_config_id, project.path
    )
    if embedding_config is None:
        raise ValueError(
            "Embedding config not found",
        )

    vector_store_config = VectorStoreConfig.from_id_and_parent_path(
        rag_config.vector_store_config_id, project.path
    )
    if vector_store_config is None:
        raise ValueError(
            "Vector store config not found",
        )

    runner = RagWorkflowRunner(
        project,
        RagWorkflowRunnerConfiguration(
            rag_config=rag_config,
            extractor_config=extractor_config,
            chunker_config=chunker_config,
            embedding_config=embedding_config,
            step_runners=[
                RagExtractionStepRunner(
                    project,
                    extractor_config,
                    concurrency=50,
                ),
                RagChunkingStepRunner(
                    project,
                    extractor_config,
                    chunker_config,
                    concurrency=50,
                ),
                RagEmbeddingStepRunner(
                    project,
                    extractor_config,
                    chunker_config,
                    embedding_config,
                    concurrency=50,
                ),
                RagIndexingStepRunner(
                    project,
                    extractor_config,
                    chunker_config,
                    embedding_config,
                    vector_store_config,
                    rag_config,
                ),
            ],
        ),
    )

    return runner
