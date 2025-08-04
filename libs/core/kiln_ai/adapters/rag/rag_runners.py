import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Callable, Generic, Tuple, TypeVar

from kiln_ai.adapters.chunkers.base_chunker import BaseChunker
from kiln_ai.adapters.chunkers.registry import chunker_adapter_from_type
from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.embedding.registry import embedding_adapter_from_type
from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, ExtractionInput
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.adapters.rag.progress import (
    LogMessage,
    RagProgress,
    compute_current_progress_for_rag_config,
)
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
from kiln_ai.utils.async_job_runner import AsyncJobRunner, AsyncJobRunnerObserver
from kiln_ai.utils.lock import asyncio_mutex
from pydantic import BaseModel, ConfigDict, Field

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


T = TypeVar("T")


class GenericErrorCollector(AsyncJobRunnerObserver[T], Generic[T]):
    def __init__(
        self,
    ):
        self.errors: list[Tuple[T, Exception]] = []

    async def on_success(self, job: T):
        pass

    async def on_error(self, job: T, error: Exception):
        self.errors.append((job, error))

    def get_errors(
        self,
        start_idx: int = 0,
    ) -> tuple[list[Tuple[T, Exception]], int]:
        """Returns a tuple of: ((job, error), index of the last error)"""
        if start_idx > 0:
            return self.errors[start_idx : len(self.errors)], len(self.errors)
        return self.errors, len(self.errors)

    def get_error_count(self) -> int:
        return len(self.errors)


class DocumentPipelineStage(str, Enum):
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"


async def execute_extractor_job(job: ExtractorJob, extractor: BaseExtractor) -> bool:
    if job.doc.path is None:
        raise ValueError("Document path is not set")

    output = await extractor.extract(
        extraction_input=ExtractionInput(
            path=job.doc.original_file.attachment.resolve_path(job.doc.path.parent),
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


async def execute_chunker_job(job: ChunkerJob, chunker: BaseChunker) -> bool:
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


async def execute_embedding_job(
    job: EmbeddingJob, embedding_adapter: BaseEmbeddingAdapter
) -> bool:
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


class AbstractRagStepRunner(ABC):
    @abstractmethod
    def stage(self) -> DocumentPipelineStage:
        pass

    # async keyword in the abstract prototype causes a type error in pyright
    # so we need to remove it, but the concrete implementation should declare async
    @abstractmethod
    def run(self) -> AsyncGenerator[RagProgress, None]:
        pass


class RagExtractionStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.lock_key = f"docs:extract:{self.extractor_config.id}"

    def stage(self) -> DocumentPipelineStage:
        return DocumentPipelineStage.EXTRACTING

    def has_extraction(self, document: Document, extractor_id: ID_TYPE) -> bool:
        for ex in document.extractions(readonly=True):
            if ex.extractor_config_id == extractor_id:
                return True
        return False

    async def collect_jobs(self) -> list[ExtractorJob]:
        jobs: list[ExtractorJob] = []
        target_extractor_config_id = self.extractor_config.id
        for document in self.project.documents(readonly=True):
            if not self.has_extraction(document, target_extractor_config_id):
                jobs.append(
                    ExtractorJob(
                        doc=document,
                        extractor_config=self.extractor_config,
                    )
                )
        return jobs

    async def run(self) -> AsyncGenerator[RagProgress, None]:
        async with asyncio_mutex(self.lock_key):
            jobs = await self.collect_jobs()
            extractor = extractor_adapter_from_type(
                self.extractor_config.extractor_type,
                self.extractor_config,
            )

            # the observer will receive and store events from the runner
            # that we can then yield from here (to keep the async generator pattern)
            observer = GenericErrorCollector()
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_extractor_job(job, extractor),
                concurrency=10,
                observers=[observer],
            )

            error_idx = 0
            async for _ in runner.run():
                yield RagProgress(
                    total_document_extracted_count=len(jobs),
                    total_document_extracted_error_count=observer.get_error_count(),
                )

                # the errors are not coming as part of the async generator yield, they are
                # accumulated in the observer, so we need to flush them manually
                if observer.get_error_count() > 0:
                    async for progress in flush_observer_errors(
                        observer,
                        lambda job,
                        error: f"Error extracting document: {job.doc.path}: {error}",
                        error_idx,
                    ):
                        yield progress
                        error_idx += 1


class RagChunkingStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        chunker_config: ChunkerConfig,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.chunker_config = chunker_config
        self.lock_key = f"docs:chunk:{self.chunker_config.id}"

    def stage(self) -> DocumentPipelineStage:
        return DocumentPipelineStage.CHUNKING

    def has_chunks(self, extraction: Extraction, chunker_id: ID_TYPE) -> bool:
        for cd in extraction.chunked_documents(readonly=True):
            if cd.chunker_config_id == chunker_id:
                return True
        return False

    async def collect_jobs(self):
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id

        jobs: list[ChunkerJob] = []
        for document in self.project.documents(readonly=True):
            extractions = document.extractions(readonly=True)
            for extraction in extractions:
                if extraction.extractor_config_id == target_extractor_config_id:
                    if not self.has_chunks(extraction, target_chunker_config_id):
                        jobs.append(
                            ChunkerJob(
                                extraction=extraction,
                                chunker_config=self.chunker_config,
                            )
                        )
        return jobs

    async def run(self) -> AsyncGenerator[RagProgress, None]:
        chunker_config = self.chunker_config
        async with asyncio_mutex(self.lock_key):
            jobs = await self.collect_jobs()
            chunker = chunker_adapter_from_type(
                chunker_config.chunker_type,
                chunker_config,
            )
            observer = GenericErrorCollector()
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_chunker_job(job, chunker),
                concurrency=10,
                observers=[observer],
            )

            error_idx = 0
            async for _ in runner.run():
                yield RagProgress(
                    total_document_chunked_count=len(jobs),
                    total_document_chunked_error_count=observer.get_error_count(),
                )

                # the errors are not coming as part of the async generator yield, they are
                # accumulated in the observer, so we need to flush them manually
                if observer.get_error_count() > 0:
                    async for progress in flush_observer_errors(
                        observer,
                        lambda job,
                        error: f"Error chunking document: {job.extraction.path}: {error}",
                        error_idx,
                    ):
                        yield progress
                        error_idx += 1


class RagEmbeddingStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        chunker_config: ChunkerConfig,
        embedding_config: EmbeddingConfig,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.chunker_config = chunker_config
        self.embedding_config = embedding_config
        self.lock_key = f"docs:embedding:{self.embedding_config.id}"

    def stage(self) -> DocumentPipelineStage:
        return DocumentPipelineStage.EMBEDDING

    def has_embeddings(self, chunked: ChunkedDocument, embedding_id: ID_TYPE) -> bool:
        for emb in chunked.chunk_embeddings(readonly=True):
            if emb.embedding_config_id == embedding_id:
                return True
        return False

    async def collect_jobs(self):
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id
        target_embedding_config_id = self.embedding_config.id

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
                                        embedding_config=self.embedding_config,
                                    )
                                )
        return jobs

    async def run(self) -> AsyncGenerator[RagProgress, None]:
        async with asyncio_mutex(self.lock_key):
            jobs = await self.collect_jobs()
            embedding_adapter = embedding_adapter_from_type(
                self.embedding_config,
            )

            observer = GenericErrorCollector()
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_embedding_job(job, embedding_adapter),
                concurrency=10,
                observers=[observer],
            )

            error_idx = 0
            async for _ in runner.run():
                yield RagProgress(
                    total_document_embedded_count=len(jobs),
                    total_document_embedded_error_count=observer.get_error_count(),
                )

                # the errors are not coming as part of the async generator yield, they are
                # accumulated in the observer, so we need to flush them manually
                if observer.get_error_count() > 0:
                    async for progress in flush_observer_errors(
                        observer,
                        lambda job,
                        error: f"Error embedding document: {job.chunked_document.path}: {error}",
                        error_idx,
                    ):
                        yield progress
                        error_idx += 1


async def flush_observer_errors(
    observer: GenericErrorCollector[T],
    error_fmt: Callable[[T, Exception], str],
    error_idx: int,
) -> AsyncGenerator[RagProgress, None]:
    errors, error_idx = observer.get_errors(error_idx)

    for job, error in errors:
        yield RagProgress(
            log=LogMessage(
                level="error",
                message=error_fmt(job, error),
            )
        )


class RagWorkflowRunnerConfiguration(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    step_runners: list[AbstractRagStepRunner] = Field(
        description="The step runners to run for the pipeline",
    )

    initial_progress: RagProgress | None = Field(
        description="The state of the pipeline before starting, if left empty the initial progress will be computed on initialization",
        default=None,
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


class RagWorkflowRunner:
    def __init__(self, project: Project, configuration: RagWorkflowRunnerConfiguration):
        self.project = project
        self.configuration = configuration
        self.step_runners: list[AbstractRagStepRunner] = configuration.step_runners
        self.initial_progress = (
            self.configuration.initial_progress
            or compute_current_progress_for_rag_config(
                self.project,
                self.configuration.rag_config,
            )
        )

    @property
    def lock_key(self) -> str:
        return f"rag:run:{self.configuration.rag_config.id}"

    def merge_progress(
        self, initial_progress: RagProgress, step_progress: RagProgress
    ) -> RagProgress:
        # initial progress is the progress of the whole pipeline when the pipeline started
        new_progress = initial_progress.model_copy()

        # incoming progress is partial cumulative progress for the step
        incoming_extracted_count = step_progress.total_document_extracted_count
        incoming_chunked_count = step_progress.total_document_chunked_count
        incoming_embedded_count = step_progress.total_document_embedded_count

        # current total progress is initial progress + incoming progress
        if incoming_extracted_count > 0:
            new_progress.total_document_extracted_count += incoming_extracted_count
        if incoming_chunked_count > 0:
            new_progress.total_document_chunked_count += incoming_chunked_count
        if incoming_embedded_count > 0:
            new_progress.total_document_embedded_count += incoming_embedded_count

        # number of fully completed documents is the same as whichever step is the least complete
        new_progress.total_document_completed_count = min(
            new_progress.total_document_extracted_count,
            new_progress.total_document_chunked_count,
            new_progress.total_document_embedded_count,
        )

        return new_progress

    async def run(
        self, stages_to_run: list[DocumentPipelineStage] | None = None
    ) -> AsyncGenerator[RagProgress, None]:
        async with asyncio_mutex(self.lock_key):
            yield self.initial_progress

            for step in self.step_runners:
                if stages_to_run is not None and step.stage() not in stages_to_run:
                    continue

                async for progress in step.run():
                    # progress coming in is the total progress but only for the step
                    # so we need to merge it with the progress of the broader pipeline
                    rag_progress = self.merge_progress(self.initial_progress, progress)
                    yield rag_progress
