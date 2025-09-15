import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Generic, List, Literal, Tuple, TypeVar

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
from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    DocumentWithChunksAndEmbeddings,
)
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


class RagStepRunnerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "complete"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    INCOMPLETE = "incomplete"


class RagWorkflowStepNames(str, Enum):
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"

    # this is a special step that is used to finalize the workflow and set the final status
    # during streaming
    ORCHESTRATION = "orchestration"


class LogMessage(BaseModel):
    level: Literal["info", "error", "warning"] = Field(
        description="The level of the log message",
    )
    message: str = Field(
        description="The message to display to the user",
    )


class RagStepRunnerProgress(BaseModel):
    step_name: RagWorkflowStepNames = Field(
        description="The name of the step runner",
    )
    status: RagStepRunnerStatus = Field(
        description="The status of the step runner",
        default=RagStepRunnerStatus.RUNNING,
    )
    expected_count: int | None = Field(
        description="The number of items that are expected to be processed. None if not known.",
        default=None,
    )
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
        default_factory=list,
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


class RagStepRunnerCounts(BaseModel):
    expected_count: int | None = Field(
        description="The number of items that are expected to be processed. None if not known or indeterminate.",
        default=None,
    )
    completed_count: int | None = Field(
        description="The number of items that have been completed. None if not known.",
        default=None,
    )


class AbstractRagStepRunner(ABC):
    @abstractmethod
    def stage(self) -> RagWorkflowStepNames:
        pass

    @abstractmethod
    async def compute_current_counts(self) -> RagStepRunnerCounts:
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
        self,
        document_ids: list[ID_TYPE] | None = None,
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

    async def compute_current_counts(self) -> RagStepRunnerCounts:
        expected_count: int = 0
        completed_count: int = 0
        target_extractor_config_id = self.extractor_config.id
        for document in self.project.documents(readonly=True):
            if self.has_extraction(document, target_extractor_config_id):
                completed_count += 1
            expected_count += 1
        return RagStepRunnerCounts(
            expected_count=expected_count, completed_count=completed_count
        )

    async def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        async with shared_async_lock_manager.acquire(self.lock_key, timeout=60):
            initial_counts = await self.compute_current_counts()
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
            cumulative_success_count = initial_counts.completed_count or 0
            cumulative_error_count = 0
            async for progress in runner.run():
                cumulative_success_count += progress.complete
                new_error_count = observer.get_error_count()
                cumulative_error_count += new_error_count
                yield RagStepRunnerProgress(
                    step_name=self.stage(),
                    status=RagStepRunnerStatus.RUNNING,
                    expected_count=initial_counts.expected_count,
                    success_count=cumulative_success_count,
                    error_count=cumulative_error_count,
                )

                # the errors are being accumulated in the observer so we need to flush them to the caller
                if new_error_count > 0:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        yield RagStepRunnerProgress(
                            step_name=self.stage(),
                            logs=[
                                LogMessage(
                                    level="error",
                                    message=f"Error extracting document: {job.doc.path}: {error}",
                                )
                            ],
                        )

            yield RagStepRunnerProgress(
                step_name=self.stage(),
                status=RagStepRunnerStatus.COMPLETED
                if cumulative_error_count == 0
                else RagStepRunnerStatus.COMPLETED_WITH_ERRORS,
                expected_count=initial_counts.expected_count,
                success_count=cumulative_success_count,
                error_count=cumulative_error_count,
            )

            if (
                cumulative_success_count + cumulative_error_count
                != initial_counts.expected_count
            ):
                logger.error(
                    "Extraction step expected count does not match the sum of success and error counts. Likely bug."
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

    async def compute_current_counts(self) -> RagStepRunnerCounts:
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id

        expected_count: int = 0
        completed_count: int = 0
        for document in self.project.documents(readonly=True):
            for extraction in deduplicate_extractions(
                document.extractions(readonly=True)
            ):
                if extraction.extractor_config_id == target_extractor_config_id:
                    if self.has_chunks(extraction, target_chunker_config_id):
                        completed_count += 1
                    expected_count += 1
        return RagStepRunnerCounts(
            expected_count=expected_count, completed_count=completed_count
        )

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
            initial_counts = await self.compute_current_counts()
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
            cumulative_success_count = initial_counts.completed_count or 0
            cumulative_error_count = 0
            async for progress in runner.run():
                cumulative_success_count += progress.complete
                new_error_count = observer.get_error_count()
                cumulative_error_count += new_error_count
                yield RagStepRunnerProgress(
                    step_name=self.stage(),
                    status=RagStepRunnerStatus.RUNNING,
                    expected_count=initial_counts.expected_count,
                    success_count=cumulative_success_count,
                    error_count=cumulative_error_count,
                )

                # the errors are being accumulated in the observer so we need to flush them to the caller
                if new_error_count > 0:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        yield RagStepRunnerProgress(
                            step_name=self.stage(),
                            logs=[
                                LogMessage(
                                    level="error",
                                    message=f"Error chunking document: {job.extraction.path}: {error}",
                                )
                            ],
                        )

            yield RagStepRunnerProgress(
                step_name=self.stage(),
                status=RagStepRunnerStatus.COMPLETED
                if cumulative_error_count == 0
                else RagStepRunnerStatus.COMPLETED_WITH_ERRORS,
                expected_count=initial_counts.expected_count,
                success_count=cumulative_success_count,
                error_count=cumulative_error_count,
            )

            if (
                cumulative_success_count + cumulative_error_count
                != initial_counts.expected_count
            ):
                logger.error(
                    "Chunking step expected count does not match the sum of success and error counts. Likely bug."
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

    async def compute_current_counts(self) -> RagStepRunnerCounts:
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id
        target_embedding_config_id = self.embedding_config.id

        expected_count: int = 0
        completed_count: int = 0
        for document in self.project.documents(readonly=True):
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
                            if self.has_embeddings(
                                chunked_document, target_embedding_config_id
                            ):
                                completed_count += 1
                            expected_count += 1
        return RagStepRunnerCounts(
            expected_count=expected_count, completed_count=completed_count
        )

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
            initial_counts = await self.compute_current_counts()
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
            cumulative_success_count = initial_counts.completed_count or 0
            cumulative_error_count = 0
            async for progress in runner.run():
                cumulative_success_count += progress.complete
                new_error_count = observer.get_error_count()
                cumulative_error_count += new_error_count
                yield RagStepRunnerProgress(
                    step_name=self.stage(),
                    status=RagStepRunnerStatus.RUNNING,
                    expected_count=initial_counts.expected_count,
                    success_count=cumulative_success_count,
                    error_count=cumulative_error_count,
                )

                # the errors are being accumulated in the observer so we need to flush them to the caller
                if new_error_count > 0:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        yield RagStepRunnerProgress(
                            step_name=self.stage(),
                            logs=[
                                LogMessage(
                                    level="error",
                                    message=f"Error embedding document: {job.chunked_document.path}: {error}",
                                )
                            ],
                        )

            yield RagStepRunnerProgress(
                step_name=self.stage(),
                status=RagStepRunnerStatus.COMPLETED
                if cumulative_error_count == 0
                else RagStepRunnerStatus.COMPLETED_WITH_ERRORS,
                expected_count=initial_counts.expected_count,
                success_count=cumulative_success_count,
                error_count=cumulative_error_count,
            )

            if (
                cumulative_success_count + cumulative_error_count
                != initial_counts.expected_count
            ):
                logger.error(
                    "Embedding step expected count does not match the sum of success and error counts. Likely bug."
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
        self.vector_store = None

    @property
    def lock_key(self) -> str:
        return f"rag:index:{self.vector_store_config.id}"

    def stage(self) -> RagWorkflowStepNames:
        return RagWorkflowStepNames.INDEXING

    async def compute_current_counts(self) -> RagStepRunnerCounts:
        logger.warning(f"Computing initial counts for {self.stage()}")
        expected_count: int = await self.count_total_chunks()
        completed_count: int = await self.count_total_chunks_indexed()
        return RagStepRunnerCounts(
            expected_count=expected_count, completed_count=completed_count
        )

    async def collect_records(
        self,
        batch_size: int,
        document_ids: list[ID_TYPE] | None = None,
    ) -> AsyncGenerator[list[DocumentWithChunksAndEmbeddings], None]:
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id
        target_embedding_config_id = self.embedding_config.id

        # (document_id, chunked_document, embedding)
        jobs: list[DocumentWithChunksAndEmbeddings] = []
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
                                        DocumentWithChunksAndEmbeddings(
                                            document_id=str(document.id),
                                            chunked_document=chunked_document,
                                            chunk_embeddings=chunk_embedding,
                                        )
                                    )

                                    if len(jobs) >= batch_size:
                                        yield jobs
                                        jobs.clear()

        if len(jobs) > 0:
            yield jobs
            jobs.clear()

    async def create_vector_store(self) -> BaseVectorStoreAdapter:
        if self.vector_store is None:
            self.vector_store = await vector_store_adapter_for_config(
                self.rag_config,
                self.vector_store_config,
            )
        return self.vector_store

    async def count_total_chunks_indexed(self) -> int:
        vector_store = await self.create_vector_store()
        return await vector_store.count_records()

    async def count_total_chunks(self) -> int:
        total_chunk_count = 0
        async for documents in self.collect_records(batch_size=1):
            total_chunk_count += len(documents[0].chunks)
        return total_chunk_count

    async def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        async with shared_async_lock_manager.acquire(self.lock_key):
            initial_counts = await self.compute_current_counts()
            vector_dimensions: int | None = None

            # infer dimensionality - we peek into the first record to get the vector dimensions
            # vector dimensions are not stored in the config because they are derived from the model
            # and in some cases dynamic shortening of the vector (called Matryoshka Representation Learning)
            async for doc_batch in self.collect_records(
                batch_size=1,
            ):
                if len(doc_batch) == 0:
                    # there are no records, because there may be nothing in the upstream steps at all yet
                    return
                else:
                    doc = doc_batch[0]
                    embedding = doc.embeddings[0]
                    vector_dimensions = len(embedding.vector)
                    break

            if vector_dimensions is None:
                raise ValueError("Vector dimensions are not set")

            vector_store = await self.create_vector_store()

            yield RagStepRunnerProgress(
                step_name=self.stage(),
                status=RagStepRunnerStatus.RUNNING,
                expected_count=initial_counts.expected_count,
                success_count=initial_counts.completed_count,
                error_count=0,
            )

            cumulative_success_count = initial_counts.completed_count or 0
            cumulative_error_count = 0
            async for doc_batch in self.collect_records(
                batch_size=self.batch_size, document_ids=document_ids
            ):
                chunk_count = 0
                for doc in doc_batch:
                    chunk_count += len(doc.chunks)

                try:
                    await vector_store.add_chunks_with_embeddings(doc_batch)
                    cumulative_success_count += chunk_count
                    yield RagStepRunnerProgress(
                        step_name=self.stage(),
                        status=RagStepRunnerStatus.RUNNING,
                        expected_count=initial_counts.expected_count,
                        success_count=cumulative_success_count,
                        error_count=cumulative_error_count,
                    )
                except Exception as e:
                    error_msg = f"Error indexing document batch starting with {doc_batch[0].document_id}: {e}"
                    logger.error(error_msg, exc_info=True)
                    cumulative_error_count += chunk_count
                    yield RagStepRunnerProgress(
                        step_name=self.stage(),
                        status=RagStepRunnerStatus.RUNNING,
                        expected_count=initial_counts.expected_count,
                        success_count=cumulative_success_count,
                        error_count=cumulative_error_count,
                        logs=[
                            LogMessage(
                                level="error",
                                message=error_msg,
                            ),
                        ],
                    )

            yield RagStepRunnerProgress(
                step_name=self.stage(),
                status=RagStepRunnerStatus.COMPLETED
                if cumulative_error_count == 0
                else RagStepRunnerStatus.COMPLETED_WITH_ERRORS,
                expected_count=initial_counts.expected_count,
                success_count=cumulative_success_count,
                error_count=cumulative_error_count,
            )

            if (
                cumulative_success_count + cumulative_error_count
                != initial_counts.expected_count
            ):
                logger.error(
                    "Indexing step expected count does not match the sum of success and error counts. Likely bug."
                )


class RagWorkflowRunnerConfiguration(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    step_runners: list[AbstractRagStepRunner] = Field(
        description="The step runners to run",
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

    @property
    def lock_key(self) -> str:
        return f"rag:run:{self.configuration.rag_config.id}"

    async def compute_current_counts(
        self,
    ) -> List[RagStepRunnerProgress]:
        logger.warning(
            f"Getting current progress for {self.configuration.rag_config.id}"
        )
        step_progresses: List[RagStepRunnerProgress] = []
        for step_progress in self.step_runners:
            logger.warning(f"Getting current progress for {step_progress.stage()}")
            initial_counts = await step_progress.compute_current_counts()
            step_progresses.append(
                RagStepRunnerProgress(
                    step_name=step_progress.stage(),
                    status=RagStepRunnerStatus.COMPLETED
                    if initial_counts.completed_count == initial_counts.expected_count
                    else RagStepRunnerStatus.INCOMPLETE,
                    expected_count=initial_counts.expected_count,
                    success_count=initial_counts.completed_count,
                    error_count=0,
                )
            )

        # overall progress is the minimum of all step counts
        overall_status = RagStepRunnerStatus.COMPLETED
        for step_progress in step_progresses:
            if step_progress.status == RagStepRunnerStatus.INCOMPLETE:
                overall_status = RagStepRunnerStatus.INCOMPLETE
                break

        number_of_documents = len(self.project.documents(readonly=True))
        step_progresses.append(
            RagStepRunnerProgress(
                step_name=RagWorkflowStepNames.ORCHESTRATION,
                status=overall_status,
                # if orchestration has a null expected count, the client thinks there are no documents to process
                expected_count=number_of_documents,
                success_count=None,
                error_count=None,
                logs=[],
            )
        )

        return step_progresses

    async def run(
        self,
        stages_to_run: list[RagWorkflowStepNames] | None = None,
        document_ids: list[ID_TYPE] | None = None,
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        """
        Runs the RAG workflow for the given stages and document ids.

        :param stages_to_run: The stages to run. If None, all stages will be run.
        :param document_ids: The document ids to run the workflow for. If None, all documents will be run.
        """
        async with shared_async_lock_manager.acquire(self.lock_key, timeout=60):
            # yield pending state for all steps
            for step in self.step_runners:
                if stages_to_run is not None and step.stage() not in stages_to_run:
                    continue

                yield RagStepRunnerProgress(
                    step_name=step.stage(),
                    status=RagStepRunnerStatus.PENDING,
                    expected_count=None,
                    success_count=None,
                    error_count=None,
                    logs=[],
                )

            last_progress_per_step: dict[
                RagWorkflowStepNames, RagStepRunnerProgress
            ] = {}
            for step in self.step_runners:
                if stages_to_run is not None and step.stage() not in stages_to_run:
                    continue

                async for progress in step.run(document_ids=document_ids):
                    last_progress_per_step[step.stage()] = progress
                    yield progress

            # yield orchestration state
            overall_status = RagStepRunnerStatus.COMPLETED
            for step in self.step_runners:
                if (
                    last_progress_per_step[step.stage()].status
                    == RagStepRunnerStatus.COMPLETED_WITH_ERRORS
                ):
                    overall_status = RagStepRunnerStatus.COMPLETED_WITH_ERRORS
                    break

            yield RagStepRunnerProgress(
                step_name=RagWorkflowStepNames.ORCHESTRATION,
                status=overall_status,
                expected_count=len(self.project.documents(readonly=True)),
                success_count=None,
                error_count=None,
                logs=[],
            )
