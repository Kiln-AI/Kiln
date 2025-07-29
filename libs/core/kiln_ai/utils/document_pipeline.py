import logging
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from kiln_ai.adapters.chunkers.base_chunker import BaseChunker
from kiln_ai.adapters.chunkers.registry import chunker_adapter_from_type
from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.embedding.registry import embedding_adapter_from_type
from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, ExtractionInput
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.datamodel import Project
from kiln_ai.datamodel.basemodel import ID_TYPE, KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument, ChunkerConfig
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding, EmbeddingConfig
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractionSource,
    ExtractorConfig,
)
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.utils.async_job_runner import AsyncJobRunner

logger = logging.getLogger(__name__)


@dataclass
class ExtractorJob:
    doc: Document
    extractor_config: ExtractorConfig


@dataclass
class ChunkerJob:
    extraction: Extraction
    chunker_config: ChunkerConfig


@dataclass
class EmbeddingJob:
    chunked_document: ChunkedDocument
    embedding_config: EmbeddingConfig


class DocumentPipelineProgress(BaseModel):
    total_count: int = Field(
        description="The total number of items to process",
        default=0,
    )

    completed_count: int = Field(
        description="The number of items that have been processed",
        default=0,
    )

    error_count: int = Field(
        description="The number of items that have errored",
        default=0,
    )

    message: str | None = Field(
        description="An arbitrary message to display to the user. For example, 'Extracting documents...', 'Chunking documents...', 'Saving embeddings...'",
        default=None,
    )


class DocumentPipelineStage(str, Enum):
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"


class AbstractPipelineObserver(ABC):
    """
    An observer for a document pipeline events; the implementation should override the event handlers.
    """

    async def on_start(self):
        """
        Called when the pipeline starts.
        """
        pass

    async def on_progress(self, progress: DocumentPipelineProgress):
        """
        Called when the pipeline makes progress.
        """
        pass

    async def on_end(self):
        """
        Called when the pipeline ends.
        """
        pass

    async def on_error(self, error: Exception):
        """
        Called when the pipeline encounters an error.
        """
        pass


class DocumentPipelineConfiguration(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    stages: Mapping[DocumentPipelineStage, bool] = Field(
        description="The stages to run in the pipeline, ordered by the order in which they should be run",
        default={
            DocumentPipelineStage.EXTRACTING: True,
            DocumentPipelineStage.CHUNKING: True,
            DocumentPipelineStage.EMBEDDING: True,
        },
    )

    rag_config: RagConfig = Field(
        description="The rag config to use for the pipeline",
    )

    extractor_config: ExtractorConfig = Field(
        description="The extractor config to use for the pipeline",
    )

    chunker_config: ChunkerConfig = Field(
        description="The chunker config to use for the pipeline",
    )

    embedding_config: EmbeddingConfig = Field(
        description="The embedding config to use for the pipeline",
    )


class DocumentPipeline:
    progress_message: str = "Initializing..."

    def __init__(self, project: Project, configuration: DocumentPipelineConfiguration):
        if not any(configuration.stages.values()):
            raise ValueError("At least one stage must be enabled")

        self.project = project
        self.configuration = configuration
        self.observers: list[AbstractPipelineObserver] = []

    def register_observers(self, observers: list[AbstractPipelineObserver]):
        for observer in observers:
            self.observers.append(observer)

    async def _notify_progress(self, progress: DocumentPipelineProgress):
        try:
            for observer in self.observers:
                await observer.on_progress(progress)
        except Exception as e:
            logger.error(f"Error notifying observers of progress: {e}", exc_info=True)

    async def _notify_start(self):
        try:
            for observer in self.observers:
                await observer.on_start()
        except Exception as e:
            logger.error(f"Error notifying observers of start: {e}", exc_info=True)

    async def _notify_end(self):
        try:
            for observer in self.observers:
                await observer.on_end()
        except Exception as e:
            logger.error(f"Error notifying observers of end: {e}", exc_info=True)

    async def _notify_error(self, error: Exception):
        try:
            for observer in self.observers:
                await observer.on_error(error)
        except Exception as e:
            logger.error(f"Error notifying observers of error: {e}", exc_info=True)

    def has_extraction(self, document: Document, extractor_id: ID_TYPE) -> bool:
        for ex in document.extractions(readonly=True):
            if ex.extractor_config_id == extractor_id:
                return True
        return False

    def has_chunks(self, extraction: Extraction, chunker_id: ID_TYPE) -> bool:
        for cd in extraction.chunked_documents(readonly=True):
            if cd.chunker_config_id == chunker_id:
                return True
        return False

    def has_embeddings(self, chunked: ChunkedDocument, embedding_id: ID_TYPE) -> bool:
        for emb in chunked.chunk_embeddings(readonly=True):
            if emb.embedding_config_id == embedding_id:
                return True
        return False

    async def collect_extraction_jobs(self) -> list[ExtractorJob]:
        await self._notify_progress(
            DocumentPipelineProgress(
                message="Preparing to extract documents...",
            )
        )

        jobs: list[ExtractorJob] = []

        target_extractor_config_id = self.configuration.extractor_config.id

        for document in self.project.documents(readonly=True):
            if not self.has_extraction(document, target_extractor_config_id):
                jobs.append(
                    ExtractorJob(
                        doc=document,
                        extractor_config=self.configuration.extractor_config,
                    )
                )

        return jobs

    async def collect_chunking_jobs(self):
        await self._notify_progress(
            DocumentPipelineProgress(
                message="Preparing to chunk extractions...",
            )
        )

        target_extractor_config_id = self.configuration.extractor_config.id
        target_chunker_config_id = self.configuration.chunker_config.id

        jobs: list[ChunkerJob] = []
        for document in self.project.documents(readonly=True):
            extractions = document.extractions(readonly=True)
            for extraction in extractions:
                if extraction.extractor_config_id == target_extractor_config_id:
                    if not self.has_chunks(extraction, target_chunker_config_id):
                        jobs.append(
                            ChunkerJob(
                                extraction=extraction,
                                chunker_config=self.configuration.chunker_config,
                            )
                        )
        return jobs

    async def collect_embedding_jobs(self):
        await self._notify_progress(
            DocumentPipelineProgress(
                message="Preparing to embed chunked documents...",
            )
        )

        target_extractor_config_id = self.configuration.extractor_config.id
        target_chunker_config_id = self.configuration.chunker_config.id
        target_embedding_config_id = self.configuration.embedding_config.id

        jobs: list[EmbeddingJob] = []
        for document in self.project.documents(readonly=True):
            extractions = document.extractions(readonly=True)
            for extraction in extractions:
                if extraction.extractor_config_id == target_extractor_config_id:
                    for chunked_document in extraction.chunked_documents(readonly=True):
                        if (
                            chunked_document.chunker_config_id
                            == target_chunker_config_id
                        ):
                            if not self.has_embeddings(
                                chunked_document, target_embedding_config_id
                            ):
                                jobs.append(
                                    EmbeddingJob(
                                        chunked_document=chunked_document,
                                        embedding_config=self.configuration.embedding_config,
                                    )
                                )
        return jobs

    async def extract(self, jobs: list[ExtractorJob], extractor: BaseExtractor):
        total_count = len(jobs)
        error_count = 0
        completed_count = 0

        async def notify_progress():
            await self._notify_progress(
                DocumentPipelineProgress(
                    message="Extracting document extractions...",
                    total_count=total_count,
                    completed_count=completed_count,
                    error_count=error_count,
                )
            )

        await notify_progress()

        # the job execution function will be run in parallel by the AsyncJobRunner
        async def job_execution_fn(job: ExtractorJob) -> bool:
            if job.doc.path is None:
                raise ValueError("Document path is not set")

            output = await extractor.extract(
                extraction_input=ExtractionInput(
                    path=job.doc.original_file.attachment.resolve_path(
                        job.doc.path.parent
                    ),
                    mime_type=job.doc.original_file.mime_type,
                )
            )

            extraction = Extraction(
                parent=job.doc,
                extractor_config_id=job.extractor_config.id,
                output=KilnAttachmentModel.from_data(
                    data=output.content,
                    mime_type=output.content_format,
                ),
                source=ExtractionSource.PASSTHROUGH
                if output.is_passthrough
                else ExtractionSource.PROCESSED,
            )
            extraction.save_to_file()
            return True

        runner = AsyncJobRunner(
            jobs=jobs,
            run_job_fn=job_execution_fn,
            concurrency=10,
            # TODO: add observers to report progress back
        )

        async for progress in runner.run():
            logger.info(f"Extraction progress: {progress}")

    async def chunk(self, jobs: list[ChunkerJob], chunker: BaseChunker):
        total_count = len(jobs)
        error_count = 0
        completed_count = 0

        async def notify_progress():
            await self._notify_progress(
                DocumentPipelineProgress(
                    message="Chunking extractions...",
                    total_count=total_count,
                    completed_count=completed_count,
                    error_count=error_count,
                )
            )

        await notify_progress()

        async def job_execution_fn(job: ChunkerJob) -> bool:
            extraction_output_content = await job.extraction.output_content()
            if extraction_output_content is None:
                raise ValueError("Extraction output content is not set")

            chunking_result = await chunker.chunk(
                extraction_output_content,
            )
            if chunking_result is None:
                raise ValueError("Chunking result is not set")

            chunked_document = ChunkedDocument(
                parent=job.extraction,
                chunker_config_id=job.chunker_config.id,
                chunks=[
                    Chunk(
                        content=KilnAttachmentModel.from_data(
                            data=chunk.text,
                            mime_type="text/plain",
                        ),
                    )
                    for chunk in chunking_result.chunks
                ],
            )
            chunked_document.save_to_file()
            return True

        runner = AsyncJobRunner(
            jobs=jobs,
            run_job_fn=job_execution_fn,
            concurrency=10,
            # TODO: add observers to report progress back
        )

        async for progress in runner.run():
            logger.info(f"Chunking progress: {progress}")

    async def generate_embeddings(
        self,
        jobs: list[EmbeddingJob],
        embedding_adapter: BaseEmbeddingAdapter,
    ):
        total_count = len(jobs)
        error_count = 0
        completed_count = 0

        async def notify_progress():
            await self._notify_progress(
                DocumentPipelineProgress(
                    message="Embedding chunked documents...",
                    total_count=total_count,
                    completed_count=completed_count,
                    error_count=error_count,
                )
            )

        await notify_progress()

        async def job_execution_fn(job: EmbeddingJob) -> bool:
            chunks_text = await job.chunked_document.load_chunks_text()
            if chunks_text is None or len(chunks_text) == 0:
                raise ValueError("No chunks text found")

            chunk_embedding_result = await embedding_adapter.generate_embeddings(
                input_texts=chunks_text
            )
            if chunk_embedding_result is None:
                raise ValueError("Chunk embedding result is not set")

            chunk_embeddings = ChunkEmbeddings(
                parent=job.chunked_document,
                embedding_config_id=job.embedding_config.id,
                embeddings=[
                    Embedding(
                        vector=embedding.vector,
                    )
                    for embedding in chunk_embedding_result.embeddings
                ],
            )

            chunk_embeddings.save_to_file()
            return True

        runner = AsyncJobRunner(
            jobs=jobs,
            run_job_fn=job_execution_fn,
            concurrency=10,
            # TODO: add observers to report progress back
        )

        async for progress in runner.run():
            logger.info(f"Embedding progress: {progress}")

    async def run(self):
        await self._notify_start()

        for stage in [
            DocumentPipelineStage.EXTRACTING,
            DocumentPipelineStage.CHUNKING,
            DocumentPipelineStage.EMBEDDING,
        ]:
            stage_enabled = self.configuration.stages.get(stage, False)
            if not stage_enabled:
                continue

            if stage == DocumentPipelineStage.EXTRACTING:
                docs = await self.collect_extraction_jobs()
                extractor = extractor_adapter_from_type(
                    self.configuration.extractor_config.extractor_type,
                    self.configuration.extractor_config,
                )
                await self.extract(docs, extractor)
            elif stage == DocumentPipelineStage.CHUNKING:
                extractions = await self.collect_chunking_jobs()
                chunker = chunker_adapter_from_type(
                    self.configuration.chunker_config.chunker_type,
                    self.configuration.chunker_config,
                )
                await self.chunk(extractions, chunker)
            elif stage == DocumentPipelineStage.EMBEDDING:
                chunked_documents = await self.collect_embedding_jobs()
                embedding_adapter = embedding_adapter_from_type(
                    self.configuration.embedding_config,
                )
                await self.generate_embeddings(chunked_documents, embedding_adapter)
            else:
                raise ValueError(f"Unknown stage: {stage}")

        await self._notify_end()
