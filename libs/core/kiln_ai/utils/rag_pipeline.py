import logging
from abc import ABC
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from kiln_ai.adapters.chunkers.base_chunker import BaseChunker
from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.extractors.base_extractor import BaseExtractor
from kiln_ai.datamodel import Project
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding
from kiln_ai.datamodel.extraction import Document, Extraction, ExtractionSource

logger = logging.getLogger(__name__)


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

    extractor: BaseExtractor = Field(
        description="The extractor to use for the pipeline",
    )

    chunker: BaseChunker = Field(
        description="The chunker to use for the pipeline",
    )

    embedding_adapter: BaseEmbeddingAdapter = Field(
        description="The embedding adapter to use for the pipeline",
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

    def is_same_extractor(self, extraction: Extraction) -> bool:
        return (
            extraction.extractor_config_id
            == self.configuration.extractor.extractor_config_id()
        )

    def is_same_chunker(self, chunked_document: ChunkedDocument) -> bool:
        return (
            chunked_document.chunker_config_id
            == self.configuration.chunker.chunker_config_id()
        )

    def is_same_embedding_adapter(self, chunk_embeddings: ChunkEmbeddings) -> bool:
        return (
            chunk_embeddings.embedding_config_id
            == self.configuration.embedding_adapter.embedding_config_id()
        )

    async def _collect_documents_to_extract(self):
        await self._notify_progress(
            DocumentPipelineProgress(
                message="Preparing to extract documents...",
            )
        )

        documents_to_extract: list[Document] = []
        for document in self.project.documents(readonly=True):
            already_extracted = any(
                self.is_same_extractor(extraction)
                for extraction in document.extractions(readonly=True)
            )
            if not already_extracted:
                documents_to_extract.append(document)

        return documents_to_extract

    async def _collect_extractions_to_chunk(self):
        await self._notify_progress(
            DocumentPipelineProgress(
                message="Preparing to chunk extractions...",
            )
        )

        extractions_to_chunk: list[Extraction] = []
        for document in self.project.documents(readonly=True):
            extractions = document.extractions(readonly=True)
            for extraction in extractions:
                if self.is_same_extractor(extraction):
                    already_chunked = any(
                        self.is_same_chunker(chunked_document)
                        for chunked_document in extraction.chunked_documents(
                            readonly=True
                        )
                    )
                    if not already_chunked:
                        extractions_to_chunk.append(extraction)

        return extractions_to_chunk

    async def _collect_chunked_documents_to_embed(self):
        await self._notify_progress(
            DocumentPipelineProgress(
                message="Preparing to embed chunked documents...",
            )
        )

        chunked_documents_to_embed: list[ChunkedDocument] = []
        for document in self.project.documents(readonly=True):
            extractions = document.extractions(readonly=True)
            for extraction in extractions:
                if self.is_same_extractor(extraction):
                    for chunked_document in extraction.chunked_documents(readonly=True):
                        if self.is_same_chunker(chunked_document):
                            already_embedded = any(
                                self.is_same_embedding_adapter(chunk_embeddings)
                                for chunk_embeddings in chunked_document.chunk_embeddings(
                                    readonly=True
                                )
                            )
                            if not already_embedded:
                                chunked_documents_to_embed.append(chunked_document)

        return chunked_documents_to_embed

    async def _run_extracting_stage(self, documents: list[Document]):
        total_count = len(documents)
        error_count = 0
        completed_count = 0

        async def notify_progress():
            await self._notify_progress(
                DocumentPipelineProgress(
                    message="Extracting documents...",
                    total_count=total_count,
                    completed_count=completed_count,
                    error_count=error_count,
                )
            )

        await notify_progress()

        for document in documents:
            if document.path is None:
                raise ValueError("Document path is not set")

            output = await self.configuration.extractor.extract(
                path=document.original_file.attachment.resolve_path(
                    document.path.parent
                ),
                mime_type=document.original_file.mime_type,
            )

            extraction = Extraction(
                parent=document,
                extractor_config_id=self.configuration.extractor.extractor_config_id(),
                output=KilnAttachmentModel.from_data(
                    data=output.content,
                    mime_type=output.content_format,
                ),
                source=ExtractionSource.PASSTHROUGH
                if output.is_passthrough
                else ExtractionSource.PROCESSED,
            )

            extraction.save_to_file()

            completed_count += 1
            await notify_progress()

    async def _run_chunking_stage(self, extractions: list[Extraction]):
        total_count = len(extractions)
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

        for extraction in extractions:
            chunker = self.configuration.chunker
            if chunker is None:
                raise ValueError("Chunker is not set")

            extraction_output_content = await extraction.output_content()
            if extraction_output_content is None:
                raise ValueError("Extraction output content is not set")

            chunking_result = await chunker.chunk(extraction_output_content)
            if chunking_result is None:
                raise ValueError("Chunking result is not set")

            chunked_document = ChunkedDocument(
                parent=extraction,
                chunker_config_id=self.configuration.chunker.chunker_config_id(),
                chunks=[
                    Chunk(
                        content=KilnAttachmentModel.from_data(
                            data=chunk.text,
                            mime_type=self.configuration.extractor.output_format(),
                        ),
                    )
                    for chunk in chunking_result.chunks
                ],
            )

            chunked_document.save_to_file()

            completed_count += 1
            await notify_progress()

    async def _run_embedding_stage(self, chunked_documents: list[ChunkedDocument]):
        total_count = len(chunked_documents)
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

        for chunked_document in chunked_documents:
            embedding_adapter = self.configuration.embedding_adapter
            if embedding_adapter is None:
                raise ValueError("Embedding adapter is not set")

            chunks_text = await chunked_document.load_chunks_text()
            if chunks_text is None or len(chunks_text) == 0:
                raise ValueError("No chunks text found")

            chunk_embedding_result = await embedding_adapter.embed(text=chunks_text)
            if chunk_embedding_result is None:
                raise ValueError("Chunk embedding result is not set")

            chunk_embeddings = ChunkEmbeddings(
                parent=chunked_document,
                embedding_config_id=self.configuration.embedding_adapter.embedding_config_id(),
                embeddings=[
                    Embedding(
                        vector=embedding.vector,
                    )
                    for embedding in chunk_embedding_result.embeddings
                ],
            )

            chunk_embeddings.save_to_file()

            completed_count += 1
            await notify_progress()

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
                docs = await self._collect_documents_to_extract()
                await self._run_extracting_stage(docs)
            elif stage == DocumentPipelineStage.CHUNKING:
                extractions = await self._collect_extractions_to_chunk()
                await self._run_chunking_stage(extractions)
            elif stage == DocumentPipelineStage.EMBEDDING:
                chunked_documents = await self._collect_chunked_documents_to_embed()
                await self._run_embedding_stage(chunked_documents)
            else:
                raise ValueError(f"Unknown stage: {stage}")

        await self._notify_end()
