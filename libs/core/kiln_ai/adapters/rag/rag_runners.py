import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, ClassVar, Generic, Set, Tuple, TypeVar

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
    filter_documents_by_tags,
)
from kiln_ai.adapters.rag.progress import LogMessage, RagProgress
from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
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
from kiln_ai.utils.filesystem_cache import FilesystemCache
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context
from kiln_ai.utils.lock import shared_async_lock_manager
from pydantic import BaseModel, ConfigDict, Field

# We set the timeout high because current UX is likely to cause the user triggering
# multiple RAG Workflows whose subconfigs (e.g. same extractor) may be shared and take
# a long time to complete, causing whichever ones are waiting on the lock to time out
# before they are likely to start.
LOCK_TIMEOUT_SECONDS = 60 * 60  # 1 hour

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
    """A single tick from a step runner. Counts are absolute totals for this
    step invocation (cumulative since the step started), not deltas. `new_logs`
    carries any log entries that surfaced since the previous tick — the
    workflow runner appends them onto the running list, so consumers see the
    full log history rather than just the latest batch.
    """

    success_count: int = Field(
        description="Items successfully processed by this step so far in this invocation.",
        default=0,
    )
    error_count: int = Field(
        description="Items that errored in this step so far in this invocation.",
        default=0,
    )
    new_logs: list[LogMessage] = Field(
        description="Log entries that appeared since the previous tick. The "
        "workflow runner appends these to the cumulative log list.",
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


class RagWorkflowStepNames(str, Enum):
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"


async def execute_extractor_job(
    job: ExtractorJob,
    extractor: BaseExtractor,
    save_context: SaveContext | None = None,
) -> bool:
    if job.doc.path is None:
        raise ValueError("Document path is not set")

    output = await extractor.extract(
        extraction_input=ExtractionInput(
            path=job.doc.original_file.attachment.resolve_path(job.doc.path.parent),
            mime_type=job.doc.original_file.mime_type,
        )
    )

    save_ctx = save_context or default_save_context
    async with save_ctx():
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


async def execute_chunker_job(
    job: ChunkerJob,
    chunker: BaseChunker,
    save_context: SaveContext | None = None,
) -> bool:
    extraction_output_content = await job.extraction.output_content()
    if extraction_output_content is None:
        raise ValueError("Extraction output content is not set")

    chunking_result = await chunker.chunk(
        extraction_output_content,
    )
    if chunking_result is None:
        raise ValueError("Chunking result is not set")

    save_ctx = save_context or default_save_context
    async with save_ctx():
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
    job: EmbeddingJob,
    embedding_adapter: BaseEmbeddingAdapter,
    save_context: SaveContext | None = None,
) -> bool:
    chunks_text = await job.chunked_document.load_chunks_text()

    # we do not raise because no chunks may be the legitimate result of the previous step
    # e.g. an empty document; a document whose content was intentionally excluded by the extraction prompt
    if chunks_text is None or len(chunks_text) == 0:
        return True

    chunk_embedding_result = await embedding_adapter.generate_embeddings(
        input_texts=chunks_text
    )
    if chunk_embedding_result is None:
        raise ValueError(
            f"Failed to generate embeddings for chunked document: {job.chunked_document.id}"
        )

    save_ctx = save_context or default_save_context
    async with save_ctx():
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
        rag_config: RagConfig | None = None,
        filesystem_cache: FilesystemCache | None = None,
        save_context: SaveContext | None = None,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.lock_key = f"docs:extract:{self.extractor_config.id}"
        self.concurrency = concurrency
        self.rag_config = rag_config
        self.filesystem_cache = filesystem_cache
        self._save_context: SaveContext = save_context or default_save_context

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

        documents = self.project.documents(readonly=True)
        if self.rag_config and self.rag_config.tags:
            documents = filter_documents_by_tags(documents, self.rag_config.tags)

        for document in documents:
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
        async with shared_async_lock_manager.acquire(
            self.lock_key, timeout=LOCK_TIMEOUT_SECONDS
        ):
            jobs = await self.collect_jobs(document_ids=document_ids)
            extractor = extractor_adapter_from_type(
                self.extractor_config.extractor_type,
                self.extractor_config,
                self.filesystem_cache,
            )

            observer = GenericErrorCollector()
            save_ctx = self._save_context
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_extractor_job(
                    job, extractor, save_context=save_ctx
                ),
                concurrency=self.concurrency,
                observers=[observer],
            )

            error_idx = 0
            async for progress in runner.run():
                # Drain any new errors observed since the last tick. Bundled
                # into the same yield as the counts — one tick per AsyncJobRunner
                # progress update, instead of interleaving log-only yields.
                new_logs: list[LogMessage] = []
                if observer.get_error_count() > error_idx:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        new_logs.append(
                            LogMessage(
                                level="error",
                                message=f"Error extracting document: {job.doc.path}: {error}",
                            )
                        )
                yield RagStepRunnerProgress(
                    success_count=progress.complete,
                    error_count=observer.get_error_count(),
                    new_logs=new_logs,
                )


class RagChunkingStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        chunker_config: ChunkerConfig,
        concurrency: int = 10,
        rag_config: RagConfig | None = None,
        save_context: SaveContext | None = None,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.chunker_config = chunker_config
        self.lock_key = f"docs:chunk:{self.chunker_config.id}"
        self.concurrency = concurrency
        self.rag_config = rag_config
        self._save_context: SaveContext = save_context or default_save_context

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
        documents = self.project.documents(readonly=True)
        if self.rag_config and self.rag_config.tags:
            documents = filter_documents_by_tags(documents, self.rag_config.tags)

        for document in documents:
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
        async with shared_async_lock_manager.acquire(
            self.lock_key, timeout=LOCK_TIMEOUT_SECONDS
        ):
            jobs = await self.collect_jobs(document_ids=document_ids)
            chunker = chunker_adapter_from_type(
                self.chunker_config.chunker_type,
                self.chunker_config,
            )
            observer = GenericErrorCollector()
            save_ctx = self._save_context
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_chunker_job(
                    job, chunker, save_context=save_ctx
                ),
                concurrency=self.concurrency,
                observers=[observer],
            )

            error_idx = 0
            async for progress in runner.run():
                new_logs: list[LogMessage] = []
                if observer.get_error_count() > error_idx:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        new_logs.append(
                            LogMessage(
                                level="error",
                                message=f"Error chunking document: {job.extraction.path}: {error}",
                            )
                        )
                yield RagStepRunnerProgress(
                    success_count=progress.complete,
                    error_count=observer.get_error_count(),
                    new_logs=new_logs,
                )


class RagEmbeddingStepRunner(AbstractRagStepRunner):
    def __init__(
        self,
        project: Project,
        extractor_config: ExtractorConfig,
        chunker_config: ChunkerConfig,
        embedding_config: EmbeddingConfig,
        concurrency: int = 10,
        rag_config: RagConfig | None = None,
        save_context: SaveContext | None = None,
    ):
        self.project = project
        self.extractor_config = extractor_config
        self.chunker_config = chunker_config
        self.embedding_config = embedding_config
        self.concurrency = concurrency
        self.rag_config = rag_config
        self.lock_key = f"docs:embedding:{self.embedding_config.id}"
        self._save_context: SaveContext = save_context or default_save_context

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
        documents = self.project.documents(readonly=True)
        if self.rag_config and self.rag_config.tags:
            documents = filter_documents_by_tags(documents, self.rag_config.tags)

        for document in documents:
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
        async with shared_async_lock_manager.acquire(
            self.lock_key, timeout=LOCK_TIMEOUT_SECONDS
        ):
            jobs = await self.collect_jobs(document_ids=document_ids)
            embedding_adapter = embedding_adapter_from_type(
                self.embedding_config,
            )

            observer = GenericErrorCollector()
            save_ctx = self._save_context
            runner = AsyncJobRunner(
                jobs=jobs,
                run_job_fn=lambda job: execute_embedding_job(
                    job, embedding_adapter, save_context=save_ctx
                ),
                concurrency=self.concurrency,
                observers=[observer],
            )

            error_idx = 0
            async for progress in runner.run():
                new_logs: list[LogMessage] = []
                if observer.get_error_count() > error_idx:
                    errors, error_idx = observer.get_errors(error_idx)
                    for job, error in errors:
                        new_logs.append(
                            LogMessage(
                                level="error",
                                message=f"Error embedding document: {job.chunked_document.path}: {error}",
                            )
                        )
                yield RagStepRunnerProgress(
                    success_count=progress.complete,
                    error_count=observer.get_error_count(),
                    new_logs=new_logs,
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
    ) -> AsyncGenerator[list[DocumentWithChunksAndEmbeddings], None]:
        target_extractor_config_id = self.extractor_config.id
        target_chunker_config_id = self.chunker_config.id
        target_embedding_config_id = self.embedding_config.id

        # (document_id, chunked_document, embedding)
        jobs: list[DocumentWithChunksAndEmbeddings] = []
        documents = self.project.documents(readonly=True)
        if self.rag_config and self.rag_config.tags:
            documents = filter_documents_by_tags(documents, self.rag_config.tags)

        for document in documents:
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

    async def count_total_chunks(self) -> int:
        total_chunk_count = 0
        async for documents in self.collect_records(batch_size=1):
            total_chunk_count += len(documents[0].chunks)
        return total_chunk_count

    def get_all_target_document_ids(self) -> Set[str]:
        documents = self.project.documents(readonly=True)
        if self.rag_config and self.rag_config.tags:
            documents = filter_documents_by_tags(documents, self.rag_config.tags)
        return {str(document.id) for document in documents}

    async def run(
        self, document_ids: list[ID_TYPE] | None = None
    ) -> AsyncGenerator[RagStepRunnerProgress, None]:
        async with shared_async_lock_manager.acquire(
            self.lock_key, timeout=LOCK_TIMEOUT_SECONDS
        ):
            found_records = False
            vector_dimensions: int | None = None

            # infer dimensionality - we peek into the first record to get the vector dimensions
            # vector dimensions are not stored in the config because they are derived from the model
            # and in some cases dynamic shortening of the vector (called Matryoshka Representation Learning)
            records_generator = self.collect_records(batch_size=1)
            try:
                async for doc_batch in records_generator:
                    doc = doc_batch[0]
                    embedding = doc.embeddings[0]
                    vector_dimensions = len(embedding.vector)
                    found_records = True
                    break
            finally:
                # since we break out early, we need to explicitly close the generator to avoid warnings
                await records_generator.aclose()

            if not found_records:
                # there are no records, because there may be nothing in the upstream steps at all yet
                yield RagStepRunnerProgress(
                    success_count=0,
                    error_count=0,
                    new_logs=[
                        LogMessage(
                            level="info",
                            message="No records to index.",
                        ),
                    ],
                )
                return

            # should not happen - we should always be throwing errors earlier if vector dimensions cannot be inferred
            if vector_dimensions is None:  # pragma: no cover
                raise ValueError("Vector dimensions are not set")

            vector_store = await vector_store_adapter_for_config(
                self.rag_config,
                self.vector_store_config,
            )

            yield RagStepRunnerProgress(
                success_count=0,
                error_count=0,
            )

            # Track cumulative counts so every yield carries the absolute total
            # for this step invocation — uniform with the other three phases,
            # which already yield cumulative counts from AsyncJobRunner.
            cumulative_success = 0
            cumulative_errors = 0
            async for doc_batch in self.collect_records(
                batch_size=self.batch_size, document_ids=document_ids
            ):
                batch_chunk_count = 0
                for doc in doc_batch:
                    batch_chunk_count += len(doc.chunks)

                try:
                    await vector_store.add_chunks_with_embeddings(doc_batch)
                    cumulative_success += batch_chunk_count
                    yield RagStepRunnerProgress(
                        success_count=cumulative_success,
                        error_count=cumulative_errors,
                    )
                except Exception as e:
                    error_msg = f"Error indexing document batch starting with {doc_batch[0].document_id}: {e}"
                    logger.error(error_msg, exc_info=True)
                    cumulative_errors += batch_chunk_count
                    yield RagStepRunnerProgress(
                        success_count=cumulative_success,
                        error_count=cumulative_errors,
                        new_logs=[
                            LogMessage(
                                level="error",
                                message=error_msg,
                            ),
                        ],
                    )

            # needed to reconcile and delete any chunks that are currently indexed but
            # are no longer in our target set (because they were deleted or untagged)
            await vector_store.delete_nodes_not_in_set(
                self.get_all_target_document_ids()
            )


class RagWorkflowRunnerConfiguration(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    step_runners: list[AbstractRagStepRunner] = Field(
        description="The step runners to run",
    )

    initial_progress: RagProgress = Field(
        description="Initial progress state provided by the caller - progress will build on top of this",
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

    # Per-phase mapping from step name to the RagProgress fields the step
    # contributes to. Each step yields cumulative counts for its invocation;
    # the workflow shifts them by the initial baseline to get overall totals.
    # Centralising the mapping here collapses the four-arm match statement
    # that used to live inside update_workflow_progress and makes adding a
    # new phase a one-line change.
    _PHASE_FIELDS: ClassVar[dict[RagWorkflowStepNames, tuple[str, str]]] = {
        RagWorkflowStepNames.EXTRACTING: (
            "total_document_extracted_count",
            "total_document_extracted_error_count",
        ),
        RagWorkflowStepNames.CHUNKING: (
            "total_document_chunked_count",
            "total_document_chunked_error_count",
        ),
        RagWorkflowStepNames.EMBEDDING: (
            "total_document_embedded_count",
            "total_document_embedded_error_count",
        ),
        RagWorkflowStepNames.INDEXING: (
            "total_chunks_indexed_count",
            "total_chunks_indexed_error_count",
        ),
    }

    def update_workflow_progress(
        self, step_name: RagWorkflowStepNames, step_progress: RagStepRunnerProgress
    ) -> RagProgress:
        if step_name not in self._PHASE_FIELDS:
            raise ValueError(f"Unhandled enum value: {step_name}")
        success_field, error_field = self._PHASE_FIELDS[step_name]

        # Step counts are absolute for THIS invocation. Add the baseline once
        # to get the overall total. (Old code used max(current, baseline+delta)
        # as a defensive monotonicity check, but with absolute counts from the
        # step runner that's redundant.)
        setattr(
            self.current_progress,
            success_field,
            getattr(self.initial_progress, success_field) + step_progress.success_count,
        )
        setattr(
            self.current_progress,
            error_field,
            getattr(self.initial_progress, error_field) + step_progress.error_count,
        )

        self.current_progress.total_document_completed_count = min(
            self.current_progress.total_document_extracted_count,
            self.current_progress.total_document_chunked_count,
            self.current_progress.total_document_embedded_count,
        )
        self.current_progress.total_chunk_completed_count = (
            self.current_progress.total_chunks_indexed_count
        )

        # Append new logs to the running list instead of replacing it. The
        # previous "replace per yield" behavior dropped all prior entries,
        # forcing callers to re-accumulate. Now `current_progress.logs` is
        # the authoritative full history.
        if step_progress.new_logs:
            self.current_progress.logs = (
                self.current_progress.logs or []
            ) + step_progress.new_logs
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
        yield self.initial_progress

        async with shared_async_lock_manager.acquire(
            self.lock_key, timeout=LOCK_TIMEOUT_SECONDS
        ):
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
                    # reset the indexing progress to 0 since we go through all the chunks again
                    if not document_ids:
                        self.initial_progress.total_chunks_indexed_count = 0
                        self.current_progress.total_chunks_indexed_count = 0

                    yield self.update_workflow_progress(
                        step.stage(),
                        RagStepRunnerProgress(
                            success_count=0,
                            error_count=0,
                        ),
                    )

                async for progress in step.run(document_ids=document_ids):
                    yield self.update_workflow_progress(step.stage(), progress)
