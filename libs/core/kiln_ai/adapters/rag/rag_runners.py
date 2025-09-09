import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Generic, Tuple, TypeVar

from kiln_ai.adapters.chunkers.base_chunker import BaseChunker
from kiln_ai.adapters.chunkers.chunker_registry import chunker_adapter_from_type
from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.embedding.embedding_registry import embedding_adapter_from_type
from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, ExtractionInput
from kiln_ai.adapters.extractors.extractor_registry import extractor_adapter_from_type
from kiln_ai.adapters.rag.deduplication import (
    deduplicate_chunk_embeddings,
    deduplicate_chunked_documents,
    deduplicate_extractions,
)
from kiln_ai.adapters.rag.progress import LogMessage, RagProgress
from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
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
from kiln_ai.datamodel.vector_store import VectorStoreConfig
from kiln_ai.utils.async_job_runner import AsyncJobRunner, AsyncJobRunnerObserver
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.lock import shared_async_lock_manager
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


class RagStepRunnerProgress(BaseModel):
    success_count: int | None = Field(
        description="The number of items that have been processed",
        default=None,
    )
    error_count: int | None = Field(
        description="The number of items that have errored",
        default=None,
    )
    logs: list[LogMessage] = Field(
        description="A list of log messages to display to the user",
        default=[],
    )


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
        if start_idx < 0:
            raise ValueError("start_idx must be non-negative")
        if start_idx >= len(self.errors):
            return [], start_idx
        if start_idx > 0:
            return self.errors[start_idx : len(self.errors)], len(self.errors)
        return self.errors, len(self.errors)

    def get_error_count(self) -> int:
        return len(self.errors)


class RagWorkflowStepNames(str, Enum):
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"


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
        raise ValueError(
            f"Failed to load chunks for chunked document: {job.chunked_document.id}"
        )

    chunk_embedding_result = await embedding_adapter.generate_embeddings(
        input_texts=chunks_text
    )
    if chunk_embedding_result is None:
        raise ValueError(
            f"Failed to generate embeddings for chunked document: {job.chunked_document.id}"
        )

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
    def stage(self) -> RagWorkflowStepNames:
        pass

    # async keyword in the abstract prototype causes a type error in pyright
    # so we need to remove it, but the concrete implementation should declare async
    @abstractmethod
    def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        pass


class RagExtractionStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        concurrency: int = 10,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.lock_key = f"docs:extract:{self.extractor_config.id}"
        self.concurrency = concurrency

    def stage(self) -> RagWorkflowStepNames:
        return RagWorkflowStepNames.EXTRACTING

    def has_extraction(self, document: Document, extractor_id: ID_TYPE) -> bool:
        for ex in document.extractions(readonly=True):
            if ex.extractor_config_id == extractor_id:
                return True
        return False

    async def collect_jobs(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> list[ExtractorJob]:
        jobs: list[ExtractorJob] = []
        target_extractor_config_id = self.extractor_config.id
        for document in self.project.documents(readonly=True):
            if (
                document_ids is not None
                and len(document_ids) > 0
                and document.id not in document_ids
            ):
                continue
            if not self.has_extraction(document, target_extractor_config_id):
                jobs.append(
                    ExtractorJob(
                        doc=document,
                        extractor_config=self.extractor_config,
                    )
                )
        return jobs

    async def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        async with shared_async_lock_manager.acquire(self.lock_key, timeout=60):
            jobs = await self.collect_jobs(document_ids=document_ids)
            extractor = extractor_adapter_from_type(
                self.extractor_config.extractor_type,
                self.extractor_config,
            )

            observer = GenericErrorCollector()
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_extractor_job(job, extractor),
                concurrency=self.concurrency,
                observers=[observer],
            )

            error_idx = 0
            async for progress in runner.run():
                yield RagStepRunnerProgress(
                    success_count=progress.complete,
                    error_count=observer.get_error_count(),
                )

                # the errors are being accumulated in the observer so we need to flush them to the caller
                if observer.get_error_count() > 0:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        yield RagStepRunnerProgress(
                            logs=[
                                LogMessage(
                                    level="error",
                                    message=f"Error extracting document: {job.doc.path}: {error}",
                                )
                            ],
                        )


class RagChunkingStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        chunker_config: ChunkerConfig,
        concurrency: int = 10,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.chunker_config = chunker_config
        self.lock_key = f"docs:chunk:{self.chunker_config.id}"
        self.concurrency = concurrency

    def stage(self) -> RagWorkflowStepNames:
        return RagWorkflowStepNames.CHUNKING

    def has_chunks(self, extraction: Extraction, chunker_id: ID_TYPE) -> bool:
        for cd in extraction.chunked_documents(readonly=True):
            if cd.chunker_config_id == chunker_id:
                return True
        return False

    async def collect_jobs(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> list[ChunkerJob]:
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id

        jobs: list[ChunkerJob] = []
        for document in self.project.documents(readonly=True):
            if (
                document_ids is not None
                and len(document_ids) > 0
                and document.id not in document_ids
            ):
                continue
            for extraction in deduplicate_extractions(
                document.extractions(readonly=True)
            ):
                if extraction.extractor_config_id == target_extractor_config_id:
                    if not self.has_chunks(extraction, target_chunker_config_id):
                        jobs.append(
                            ChunkerJob(
                                extraction=extraction,
                                chunker_config=self.chunker_config,
                            )
                        )
        return jobs

    async def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        async with shared_async_lock_manager.acquire(self.lock_key, timeout=60):
            jobs = await self.collect_jobs(document_ids=document_ids)
            chunker = chunker_adapter_from_type(
                self.chunker_config.chunker_type,
                self.chunker_config,
            )
            observer = GenericErrorCollector()
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_chunker_job(job, chunker),
                concurrency=self.concurrency,
                observers=[observer],
            )

            error_idx = 0
            async for progress in runner.run():
                yield RagStepRunnerProgress(
                    success_count=progress.complete,
                    error_count=observer.get_error_count(),
                )

                # the errors are being accumulated in the observer so we need to flush them to the caller
                if observer.get_error_count() > 0:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        yield RagStepRunnerProgress(
                            logs=[
                                LogMessage(
                                    level="error",
                                    message=f"Error chunking document: {job.extraction.path}: {error}",
                                )
                            ],
                        )


class RagEmbeddingStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        chunker_config: ChunkerConfig,
        embedding_config: EmbeddingConfig,
        concurrency: int = 10,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.chunker_config = chunker_config
        self.embedding_config = embedding_config
        self.concurrency = concurrency
        self.lock_key = f"docs:embedding:{self.embedding_config.id}"

    def stage(self) -> RagWorkflowStepNames:
        return RagWorkflowStepNames.EMBEDDING

    def has_embeddings(self, chunked: ChunkedDocument, embedding_id: ID_TYPE) -> bool:
        for emb in chunked.chunk_embeddings(readonly=True):
            if emb.embedding_config_id == embedding_id:
                return True
        return False

    async def collect_jobs(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> list[EmbeddingJob]:
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id
        target_embedding_config_id = self.embedding_config.id

        jobs: list[EmbeddingJob] = []
        for document in self.project.documents(readonly=True):
            if (
                document_ids is not None
                and len(document_ids) > 0
                and document.id not in document_ids
            ):
                continue
            for extraction in deduplicate_extractions(
                document.extractions(readonly=True)
            ):
                if extraction.extractor_config_id == target_extractor_config_id:
                    for chunked_document in deduplicate_chunked_documents(
                        extraction.chunked_documents(readonly=True)
                    ):
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

    async def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        async with shared_async_lock_manager.acquire(self.lock_key, timeout=60):
            jobs = await self.collect_jobs(document_ids=document_ids)
            embedding_adapter = embedding_adapter_from_type(
                self.embedding_config,
            )

            observer = GenericErrorCollector()
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_embedding_job(job, embedding_adapter),
                concurrency=self.concurrency,
                observers=[observer],
            )

            error_idx = 0
            async for progress in runner.run():
                yield RagStepRunnerProgress(
                    success_count=progress.complete,
                    error_count=observer.get_error_count(),
                )

                # the errors are being accumulated in the observer so we need to flush them to the caller
                if observer.get_error_count() > 0:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        yield RagStepRunnerProgress(
                            logs=[
                                LogMessage(
                                    level="error",
                                    message=f"Error embedding document: {job.chunked_document.path}: {error}",
                                )
                            ],
                        )


class RagIndexingStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        chunker_config: ChunkerConfig,
        embedding_config: EmbeddingConfig,
        vector_store_config: VectorStoreConfig,
        rag_config: RagConfig,
        concurrency: int = 10,
        batch_size: int = 20,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.chunker_config = chunker_config
        self.embedding_config = embedding_config
        self.vector_store_config = vector_store_config
        self.rag_config = rag_config
        self.concurrency = concurrency
        self.batch_size = batch_size

    @property
    def lock_key(self) -> str:
        return f"rag:index:{self.vector_store_config.id}"

    def stage(self) -> RagWorkflowStepNames:
        return RagWorkflowStepNames.INDEXING

    async def collect_records(
        self,
        batch_size: int,
        document_ids: list[ID_TYPE] | None = None,
    ) -> AsyncGenerator[list[Tuple[str, ChunkedDocument, ChunkEmbeddings]], None]:
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id
        target_embedding_config_id = self.embedding_config.id

        # (document_id, chunked_document, embedding)
        jobs: list[Tuple[str, ChunkedDocument, ChunkEmbeddings]] = []
        for document in self.project.documents(readonly=True):
            if (
                document_ids is not None
                and len(document_ids) > 0
                and document.id not in document_ids
            ):
                continue
            for extraction in deduplicate_extractions(
                document.extractions(readonly=True)
            ):
                if extraction.extractor_config_id == target_extractor_config_id:
                    for chunked_document in deduplicate_chunked_documents(
                        extraction.chunked_documents(readonly=True)
                    ):
                        if (
                            chunked_document.chunker_config_id
                            == target_chunker_config_id
                        ):
                            for chunk_embedding in deduplicate_chunk_embeddings(
                                chunked_document.chunk_embeddings(readonly=True)
                            ):
                                if (
                                    chunk_embedding.embedding_config_id
                                    == target_embedding_config_id
                                ):
                                    jobs.append(
                                        (
                                            str(document.id),
                                            chunked_document,
                                            chunk_embedding,
                                        )
                                    )

                                    if len(jobs) >= batch_size:
                                        yield jobs
                                        jobs.clear()

        if len(jobs) > 0:
            yield jobs
            jobs.clear()

    async def count_total_chunks(self) -> int:
        total_chunk_count = 0
        async for records in self.collect_records(batch_size=1):
            _, chunked_doc, _ = records[0]
            total_chunk_count += len(chunked_doc.chunks)
        return total_chunk_count

    async def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        async with shared_async_lock_manager.acquire(self.lock_key):
            vector_dimensions: int | None = None

            # infer dimensionality - we peek into the first record to get the vector dimensions
            # vector dimensions are not stored in the config because they are derived from the model
            # and in some cases dynamic shortening of the vector (OpenAI has this)
            async for records in self.collect_records(
                batch_size=1,
            ):
                if len(records) == 0:
                    # there are no records, because there may be nothing in the upstream steps at all yet
                    return
                else:
                    embedding = records[0][2].embeddings[0]
                    vector_dimensions = len(embedding.vector)
                    break

            if vector_dimensions is None:
                raise ValueError("Vector dimensions are not set")

            vector_store = await vector_store_adapter_for_config(
                self.rag_config,
                self.vector_store_config,
            )

            yield RagStepRunnerProgress(
                success_count=0,
                error_count=0,
            )

            indexed_count = 0
            async for records in self.collect_records(
                batch_size=self.batch_size, document_ids=document_ids
            ):
                chunk_count = 0
                for record in records:
                    chunk_count += len(record[1].chunks)

                try:
                    await vector_store.add_chunks_with_embeddings(records)
                    indexed_count += chunk_count
                    yield RagStepRunnerProgress(
                        success_count=chunk_count,
                        error_count=0,
                    )
                except Exception as e:
                    error_msg = f"Error indexing document batch starting with {records[0][0]}: {e}"
                    logger.error(error_msg, exc_info=True)
                    yield RagStepRunnerProgress(
                        success_count=0,
                        error_count=chunk_count,
                        logs=[
                            LogMessage(
                                level="error",
                                message=error_msg,
                            ),
                        ],
                    )


class RagWorkflowRunnerConfiguration(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    step_runners: list[AbstractRagStepRunner] = Field(
        description="The step runners to run",
    )

    initial_progress: RagProgress = Field(
        description="The state of the workflow before starting, if left empty the initial progress will be computed on initialization",
    )

    rag_config: RagConfig = Field(
        description="The rag config to use for the workflow",
    )

    extractor_config: ExtractorConfig = Field(
        description="The extractor config to use for the workflow",
    )

    chunker_config: ChunkerConfig = Field(
        description="The chunker config to use for the workflow",
    )

    embedding_config: EmbeddingConfig = Field(
        description="The embedding config to use for the workflow",
    )


class RagWorkflowRunner:
    def __init__(
        self,
        project: Project,
        configuration: RagWorkflowRunnerConfiguration,
    ):
        self.project = project
        self.configuration = configuration
        self.step_runners: list[AbstractRagStepRunner] = configuration.step_runners
        self.initial_progress = self.configuration.initial_progress
        self.current_progress = self.initial_progress.model_copy()

    @property
    def lock_key(self) -> str:
        return f"rag:run:{self.configuration.rag_config.id}"

    def update_workflow_progress(
        self, step_name: RagWorkflowStepNames, step_progress: RagStepRunnerProgress
    ) -> RagProgress:
        # merge the simpler step-specific progress with the broader RAG progress
        match step_name:
            case RagWorkflowStepNames.EXTRACTING:
                if step_progress.success_count is not None:
                    self.current_progress.total_document_extracted_count = max(
                        self.current_progress.total_document_extracted_count,
                        step_progress.success_count
                        + self.initial_progress.total_document_extracted_count,
                    )
                if step_progress.error_count is not None:
                    self.current_progress.total_document_extracted_error_count = max(
                        self.current_progress.total_document_extracted_error_count,
                        step_progress.error_count
                        + self.initial_progress.total_document_extracted_error_count,
                    )
            case RagWorkflowStepNames.CHUNKING:
                if step_progress.success_count is not None:
                    self.current_progress.total_document_chunked_count = max(
                        self.current_progress.total_document_chunked_count,
                        step_progress.success_count
                        + self.initial_progress.total_document_chunked_count,
                    )
                if step_progress.error_count is not None:
                    self.current_progress.total_document_chunked_error_count = max(
                        self.current_progress.total_document_chunked_error_count,
                        step_progress.error_count
                        + self.initial_progress.total_document_chunked_error_count,
                    )
            case RagWorkflowStepNames.EMBEDDING:
                if step_progress.success_count is not None:
                    self.current_progress.total_document_embedded_count = max(
                        self.current_progress.total_document_embedded_count,
                        step_progress.success_count
                        + self.initial_progress.total_document_embedded_count,
                    )
                if step_progress.error_count is not None:
                    self.current_progress.total_document_embedded_error_count = max(
                        self.current_progress.total_document_embedded_error_count,
                        step_progress.error_count
                        + self.initial_progress.total_document_embedded_error_count,
                    )
            case RagWorkflowStepNames.INDEXING:
                if step_progress.success_count is not None:
                    self.current_progress.total_chunks_indexed_count = (
                        self.current_progress.total_chunks_indexed_count
                        + step_progress.success_count
                    )
                if step_progress.error_count is not None:
                    self.current_progress.total_chunks_indexed_error_count = max(
                        self.current_progress.total_chunks_indexed_error_count,
                        step_progress.error_count
                        + self.initial_progress.total_chunks_indexed_error_count,
                    )
            case _:
                raise_exhaustive_enum_error(step_name)

        self.current_progress.total_document_completed_count = min(
            self.current_progress.total_document_extracted_count,
            self.current_progress.total_document_chunked_count,
            self.current_progress.total_document_embedded_count,
        )

        self.current_progress.total_chunk_completed_count = (
            self.current_progress.total_chunks_indexed_count
        )

        self.current_progress.logs = step_progress.logs
        return self.current_progress

    async def run(
        self,
        stages_to_run: list[RagWorkflowStepNames] | None = None,
        document_ids: list[ID_TYPE] | None = None,
    ) -> AsyncGenerator[RagProgress, None]:
        """
        Runs the RAG workflow for the given stages and document ids.

        :param stages_to_run: The stages to run. If None, all stages will be run.
        :param document_ids: The document ids to run the workflow for. If None, all documents will be run.
        """
        async with shared_async_lock_manager.acquire(self.lock_key, timeout=60):
            yield self.initial_progress

            for step in self.step_runners:
                if stages_to_run is not None and step.stage() not in stages_to_run:
                    continue

                # we need to know the total number of chunks to index to be able to
                # calculate the progress on the client
                if step.stage() == RagWorkflowStepNames.INDEXING and isinstance(
                    step, RagIndexingStepRunner
                ):
                    self.current_progress.total_chunk_count = (
                        await step.count_total_chunks()
                    )

                async for progress in step.run(document_ids=document_ids):
                    yield self.update_workflow_progress(step.stage(), progress)
