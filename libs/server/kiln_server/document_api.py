import asyncio
import datetime
import json
import logging
from typing import Annotated, Awaitable, Callable, Dict, List, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from kiln_ai.adapters.embedding.embedding_registry import embedding_adapter_from_type
from kiln_ai.adapters.extractors.extractor_registry import extractor_adapter_from_type
from kiln_ai.adapters.extractors.extractor_runner import ExtractorRunner
from kiln_ai.adapters.ml_embedding_model_list import (
    EmbeddingModelName,
    built_in_embedding_models_from_provider,
)
from kiln_ai.adapters.ml_model_list import built_in_models_from_provider
from kiln_ai.adapters.rag.progress import (
    LogMessage,
    RagProgress,
    compute_current_progress_for_rag_config,
    compute_current_progress_for_rag_configs,
)
from kiln_ai.adapters.rag.rag_runners import (
    RagChunkingStepRunner,
    RagEmbeddingStepRunner,
    RagExtractionStepRunner,
    RagIndexingStepRunner,
    RagWorkflowRunner,
    RagWorkflowRunnerConfiguration,
)
from kiln_ai.adapters.reranker_list import built_in_reranker_models_from_provider
from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    SearchResult,
    VectorStoreQuery,
)
from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    FilenameString,
    KilnAttachmentModel,
    string_to_valid_name,
)
from kiln_ai.datamodel.chunk import (
    ChunkerConfig,
    ChunkerType,
    FixedWindowChunkerProperties,
    SemanticChunkerProperties,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig, EmbeddingProperties
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractorConfig,
    ExtractorType,
    FileInfo,
    LitellmExtractorConfigProperties,
    OutputFormat,
    get_kind_from_mime_type,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.reranker import (
    CohereCompatibleProperties,
    RerankerConfig,
    RerankerType,
)
from kiln_ai.datamodel.vector_store import (
    LanceDBConfigFTSProperties,
    LanceDBConfigHybridProperties,
    LanceDBConfigVectorProperties,
    VectorStoreConfig,
    VectorStoreType,
)
from kiln_ai.utils import shared_async_lock_manager
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.filesystem import open_folder
from kiln_ai.utils.filesystem_cache import TemporaryFilesystemCache
from kiln_ai.utils.mime_type import guess_mime_type
from kiln_ai.utils.name_generator import generate_memorable_name
from pydantic import BaseModel, Field, PositiveInt, model_validator

from kiln_server.project_api import project_from_id

logger = logging.getLogger(__name__)

background_tasks: set[asyncio.Task] = set()


class BulkCreateDocumentsResponse(BaseModel):
    created_documents: List[Document]
    failed_files: List[str]


def get_rag_config_from_id(project: Project, rag_config_id: str) -> RagConfig:
    rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
    if rag_config is None:
        raise HTTPException(
            status_code=404,
            detail="RAG config not found",
        )
    return rag_config


async def run_extractor_runner_with_status(
    extractor_runner: ExtractorRunner,
) -> StreamingResponse:
    # Yields async messages designed to be used with server sent events (SSE)
    # https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
    async def event_generator():
        async for progress in extractor_runner.run():
            data = {
                "progress": progress.complete,
                "total": progress.total,
                "errors": progress.errors,
            }
            yield f"data: {json.dumps(data)}\n\n"

        # Send the final complete message the app expects, and uses to stop listening
        yield "data: complete\n\n"

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
    )


async def run_rag_workflow_runner_with_status(
    runner_factory: Callable[[], Awaitable[RagWorkflowRunner]],
) -> StreamingResponse:
    async def event_generator():
        latest_progress = RagProgress()

        def serialize_progress(progress: RagProgress):
            logs = []
            for log in progress.logs or []:
                logs.append(
                    {
                        "message": log.message,
                        "level": log.level,
                    }
                )

            data = {
                "total_document_completed_count": progress.total_document_completed_count,
                "total_document_count": progress.total_document_count,
                "total_chunk_count": progress.total_chunk_count,
                "total_chunk_completed_count": progress.total_chunk_completed_count,
                "total_document_extracted_count": progress.total_document_extracted_count,
                "total_document_chunked_count": progress.total_document_chunked_count,
                "total_document_embedded_count": progress.total_document_embedded_count,
                "total_document_extracted_error_count": progress.total_document_extracted_error_count,
                "total_document_chunked_error_count": progress.total_document_chunked_error_count,
                "total_document_embedded_error_count": progress.total_document_embedded_error_count,
                "total_chunks_indexed_count": progress.total_chunks_indexed_count,
                "total_chunks_indexed_error_count": progress.total_chunks_indexed_error_count,
                "logs": logs,
            }
            return data

        try:
            # we initialize the runner inside the wrapper to surface errors to the frontend via logging UI
            # we do it via a factory to allow for easier mocking in tests
            runner = await runner_factory()
            async for progress in runner.run():
                latest_progress = progress.model_copy()
                data = serialize_progress(progress)
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.TimeoutError:
            logger.info("RAG workflow runner cancelled")
            latest_progress.logs = [
                LogMessage(
                    level="error",
                    message="Timed out after waiting for the lock to be acquired. This may be due to a concurrent RAG workflow running. You may retry in a few minutes.",
                )
            ]
            data = serialize_progress(latest_progress)
            yield f"data: {json.dumps(data)}\n\n"
        except Exception as e:
            logger.error(
                f"Unexpected server error running RAG workflow runner: {e}",
                exc_info=True,
            )
            latest_progress.logs = [
                LogMessage(
                    level="error",
                    message=f"Unexpected server error: {e}",
                )
            ]
            data = serialize_progress(latest_progress)
            yield f"data: {json.dumps(data)}\n\n"

        # Send the final complete message the app expects, and uses to stop listening
        yield "data: complete\n\n"

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
    )


class OpenFileResponse(BaseModel):
    path: str


class ExtractionProgress(BaseModel):
    document_count_total: int
    document_count_successful: int
    extractor_config: ExtractorConfig | None


class ExtractorSummary(BaseModel):
    id: str
    name: str
    description: str | None
    output_format: OutputFormat
    passthrough_mimetypes: list[OutputFormat]
    extractor_type: ExtractorType


class ExtractionSummary(BaseModel):
    id: str
    created_at: datetime.datetime
    created_by: str
    source: str
    output_content: str
    extractor: ExtractorSummary


class RagConfigWithSubConfigs(BaseModel):
    id: ID_TYPE
    name: str
    description: str | None
    tool_name: str
    tool_description: str
    created_at: datetime.datetime
    created_by: str
    is_archived: bool
    extractor_config: ExtractorConfig
    chunker_config: ChunkerConfig
    embedding_config: EmbeddingConfig
    vector_store_config: VectorStoreConfig
    reranker_config: RerankerConfig | None
    tags: list[str] | None


class CreateRagConfigRequest(BaseModel):
    name: FilenameString | None = Field(
        description="A name for this entity.",
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="A description for your own reference.",
        default=None,
    )
    tool_name: str = Field(
        description="A name for the model to identify the Search Tool in conversations.",
    )
    tool_description: str = Field(
        description="A description of the purpose of the tool. The model will use this description to understand the tool's capabilities.",
    )
    extractor_config_id: ID_TYPE = Field(
        description="The extractor config to use for the RAG workflow",
    )
    chunker_config_id: ID_TYPE = Field(
        description="The chunker config to use for the RAG workflow.",
    )
    embedding_config_id: ID_TYPE = Field(
        description="The embedding config to use for the RAG workflow.",
    )
    vector_store_config_id: ID_TYPE = Field(
        description="The vector store config to use for the RAG workflow.",
    )
    reranker_config_id: ID_TYPE | None = Field(
        description="The reranker config to use for the RAG workflow.",
        default=None,
    )
    tags: list[str] | None = Field(
        description="List of document tags to filter by. If None, all documents in the project are used.",
        default=None,
    )


class SemanticChunkerPropertiesPublic(BaseModel):
    chunker_type: Literal[ChunkerType.SEMANTIC] = Field(
        description="The type of the chunker",
    )
    embedding_config_id: str = Field(
        description="The embedding config to use for the RAG workflow.",
    )
    buffer_size: int = Field(
        description="The buffer size to use for the chunker.",
    )
    breakpoint_percentile_threshold: int = Field(
        description="The breakpoint percentile threshold to use for the chunker.",
    )


class FixedWindowChunkerPropertiesPublic(BaseModel):
    chunker_type: Literal[ChunkerType.FIXED_WINDOW] = Field(
        description="The type of the chunker",
    )
    chunk_size: int = Field(
        description="The chunk size to use for the chunker.",
    )
    chunk_overlap: int = Field(
        description="The chunk overlap to use for the chunker.",
    )


class CreateChunkerConfigRequest(BaseModel):
    name: FilenameString | None = Field(
        description="A name for this entity.",
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="The description of the chunker config",
        default=None,
    )
    chunker_type: ChunkerType = Field(
        description="The type of the chunker",
    )
    properties: SemanticChunkerPropertiesPublic | FixedWindowChunkerPropertiesPublic = (
        Field(
            discriminator="chunker_type",
        )
    )

    def get_properties_for_chunker_type(
        self,
    ) -> SemanticChunkerProperties | FixedWindowChunkerProperties:
        properties = self.properties
        match properties.chunker_type:
            case ChunkerType.SEMANTIC:
                return SemanticChunkerProperties(
                    chunker_type=ChunkerType.SEMANTIC,
                    embedding_config_id=properties.embedding_config_id,
                    buffer_size=properties.buffer_size,
                    breakpoint_percentile_threshold=properties.breakpoint_percentile_threshold,
                    include_metadata=False,
                    include_prev_next_rel=False,
                )
            case ChunkerType.FIXED_WINDOW:
                return FixedWindowChunkerProperties(
                    chunker_type=ChunkerType.FIXED_WINDOW,
                    chunk_size=properties.chunk_size,
                    chunk_overlap=properties.chunk_overlap,
                )
        raise_exhaustive_enum_error(properties.chunker_type)


class CreateEmbeddingConfigRequest(BaseModel):
    name: FilenameString | None = Field(
        description="A name for this entity.",
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="The description of the embedding config",
        default=None,
    )
    model_provider_name: ModelProviderName = Field(
        description="The provider of the embedding model",
    )
    model_name: EmbeddingModelName = Field(
        description="The name of the embedding model",
    )
    properties: EmbeddingProperties = Field(
        default_factory=lambda: {},
        description="Properties to be used to execute the embedding config.",
    )

    @model_validator(mode="after")
    def validate_properties(self):
        model = built_in_embedding_models_from_provider(
            provider_name=self.model_provider_name,
            model_name=self.model_name,
        )
        if model is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model {self.model_name} not found in {self.model_provider_name}",
            )

        if "dimensions" in self.properties:
            if self.properties["dimensions"] > model.n_dimensions:
                raise HTTPException(
                    status_code=422,
                    detail="Dimensions must be less than the model's dimensions",
                )

        return self


# the publicly exposed properties of each vector store config type happen to be the same right now
# but we keep them separate to make it easier to add new properties in the future as they
# can drift independently
class LanceDBConfigFTSPropertiesPublic(BaseModel):
    similarity_top_k: int = Field(
        description="The number of results to return from the vector store.",
    )


class LanceDBConfigVectorPropertiesPublic(BaseModel):
    similarity_top_k: int = Field(
        description="The number of results to return from the vector store.",
    )


class LanceDBConfigHybridPropertiesPublic(BaseModel):
    similarity_top_k: int = Field(
        description="The number of results to return from the vector store.",
    )


class CreateVectorStoreConfigRequest(BaseModel):
    name: FilenameString | None = Field(
        description="A name for this entity.",
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="The description of the vector store config",
        default=None,
    )
    store_type: VectorStoreType = Field(
        description="The type of vector store to use",
    )
    properties: (
        LanceDBConfigFTSPropertiesPublic
        | LanceDBConfigVectorPropertiesPublic
        | LanceDBConfigHybridPropertiesPublic
    ) = Field(
        description="The properties of the vector store config, specific to the selected store_type."
    )

    def get_properties_for_store_type(
        self,
    ) -> (
        LanceDBConfigFTSProperties
        | LanceDBConfigVectorProperties
        | LanceDBConfigHybridProperties
    ):
        """
        Returns the properties for the vector store config, with the right type and set
        some default values for the fields we do not expose to the UI
        """
        match self.store_type:
            case VectorStoreType.LANCE_DB_FTS:
                return LanceDBConfigFTSProperties(
                    store_type=VectorStoreType.LANCE_DB_FTS,
                    similarity_top_k=self.properties.similarity_top_k,
                    overfetch_factor=1,
                    vector_column_name="vector",
                    text_key="text",
                    doc_id_key="doc_id",
                )
            case VectorStoreType.LANCE_DB_VECTOR:
                return LanceDBConfigVectorProperties(
                    store_type=VectorStoreType.LANCE_DB_VECTOR,
                    similarity_top_k=self.properties.similarity_top_k,
                    overfetch_factor=1,
                    vector_column_name="vector",
                    text_key="text",
                    doc_id_key="doc_id",
                    nprobes=20,
                )
            case VectorStoreType.LANCE_DB_HYBRID:
                return LanceDBConfigHybridProperties(
                    store_type=VectorStoreType.LANCE_DB_HYBRID,
                    similarity_top_k=self.properties.similarity_top_k,
                    overfetch_factor=1,
                    vector_column_name="vector",
                    text_key="text",
                    doc_id_key="doc_id",
                    nprobes=20,
                )
            case _:
                raise_exhaustive_enum_error(self.store_type)


class CreateRerankerConfigRequest(BaseModel):
    name: FilenameString | None = Field(
        description="A name for this entity.",
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="The description of the reranker config",
        default=None,
    )
    top_n: PositiveInt = Field(
        description="Number of results to return from the reranker"
    )
    model_provider_name: ModelProviderName = Field(
        description="The name of the model provider to use for the reranker config.",
    )
    model_name: str = Field(
        description="The name of the model to use for the reranker config.",
    )
    properties: CohereCompatibleProperties = Field(
        description="The properties of the reranker config.",
        default=CohereCompatibleProperties(
            type=RerankerType.COHERE_COMPATIBLE,
        ),
    )

    @model_validator(mode="after")
    def validate_properties(self):
        # check the reranker exists
        model = built_in_reranker_models_from_provider(
            provider_name=self.model_provider_name,
            model_name=self.model_name,
        )
        if model is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model {self.model_name} not found in {self.model_provider_name}",
            )

        return self

    def get_reranker_config_properties(self) -> CohereCompatibleProperties:
        # currently only one type is supported, but we may add more in the future
        match self.properties.get("type"):
            case RerankerType.COHERE_COMPATIBLE:
                return CohereCompatibleProperties(
                    type=RerankerType.COHERE_COMPATIBLE,
                )
            case _:
                raise ValueError(
                    f"Invalid reranker type: {self.properties.get('type')}"
                )


class CreateExtractorConfigRequest(BaseModel):
    name: FilenameString | None = Field(
        description="A name for this entity.",
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="The description of the extractor config",
        default=None,
    )
    model_provider_name: ModelProviderName = Field(
        description="The name of the model provider to use for the extractor config.",
    )
    model_name: str = Field(
        description="The name of the model to use for the extractor config.",
    )
    output_format: OutputFormat = Field(
        description="The output format of the extractor config",
    )
    passthrough_mimetypes: list[OutputFormat] = Field(
        description="The mimetypes to pass through to the extractor",
        default_factory=list,
    )
    properties: LitellmExtractorConfigProperties = Field(
        description="The properties of the extractor config, specific to the selected extractor_type.",
    )

    @model_validator(mode="after")
    def validate_properties(self):
        try:
            typed_model_provider_name = ModelProviderName(self.model_provider_name)
        except ValueError:
            raise ValueError(f"Invalid model provider name: {self.model_provider_name}")

        # check the model exists and is suitable as an extractor
        model = built_in_models_from_provider(
            provider_name=typed_model_provider_name,
            model_name=self.model_name,
        )

        if model is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model {self.model_name} not found in {self.model_provider_name}",
            )

        if not model.supports_doc_extraction:
            raise ValueError(
                f"Model {self.model_name} does not support document extraction"
            )

        return self

    def get_properties(self) -> LitellmExtractorConfigProperties:
        match self.properties["extractor_type"]:
            case ExtractorType.LITELLM:
                return LitellmExtractorConfigProperties(
                    extractor_type=ExtractorType.LITELLM,
                    prompt_document=self.properties["prompt_document"],
                    prompt_image=self.properties["prompt_image"],
                    prompt_video=self.properties["prompt_video"],
                    prompt_audio=self.properties["prompt_audio"],
                )
            case _:
                raise_exhaustive_enum_error(self.properties["extractor_type"])


class PatchDocumentRequest(BaseModel):
    name_override: str | None = Field(
        description="A name for this document.",
        default=None,
    )
    description: str | None = Field(
        description="The description of the document",
        default=None,
    )
    tags: list[str] | None = Field(
        description="Tags for the document",
        default=None,
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if all(
            field is None for field in [self.name_override, self.description, self.tags]
        ):
            raise ValueError("At least one field must be provided")
        return self

    @model_validator(mode="after")
    def validate_tags(self):
        if self.tags is not None:
            for tag in self.tags:
                if not tag:
                    raise ValueError("Tags cannot be empty strings")
                if " " in tag:
                    raise ValueError("Tags cannot contain spaces. Try underscores.")
        return self


class PatchExtractorConfigRequest(BaseModel):
    name: FilenameString | None = Field(
        description="A name for this entity.",
        default=None,
    )
    description: str | None = Field(
        description="The description of the extractor config",
        default=None,
    )
    is_archived: bool | None = Field(
        description="Whether the extractor config is archived",
        default=None,
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if all(
            field is None for field in [self.name, self.description, self.is_archived]
        ):
            raise ValueError("At least one field must be provided")
        return self


class UpdateRagConfigRequest(BaseModel):
    name: FilenameString | None = None
    description: str | None = None
    is_archived: bool | None = None


def build_extraction_summary(
    extraction: Extraction,
    output_content: str | None,
    extractor_config: ExtractorConfig,
) -> ExtractionSummary:
    return ExtractionSummary(
        id=str(extraction.id),
        created_at=extraction.created_at,
        created_by=extraction.created_by,
        source=extraction.source,
        output_content=output_content or "",
        extractor=ExtractorSummary(
            id=str(extractor_config.id),
            name=extractor_config.name,
            description=extractor_config.description,
            output_format=extractor_config.output_format,
            passthrough_mimetypes=extractor_config.passthrough_mimetypes,
            extractor_type=extractor_config.extractor_type,
        ),
    )


class GetRagConfigProgressRequest(BaseModel):
    rag_config_ids: list[str] | None = Field(
        description="The RAG config ids to get progress for, if left empty, progress for all RAG configs in the project will be returned",
        default=None,
    )


class RagSearchRequest(BaseModel):
    query: str = Field(
        description="The search query text",
    )


class RagSearchResponse(BaseModel):
    results: list[SearchResult] = Field(
        description="The search results",
    )


async def build_rag_workflow_runner(
    project: Project,
    rag_config_id: str,
) -> RagWorkflowRunner:
    rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
    if rag_config is None:
        raise HTTPException(
            status_code=404,
            detail="RAG config not found",
        )

    # should not happen, but id is optional in the datamodel
    if (
        rag_config.extractor_config_id is None
        or rag_config.chunker_config_id is None
        or rag_config.embedding_config_id is None
        or rag_config.vector_store_config_id is None
    ):
        raise HTTPException(
            status_code=400,
            detail="RAG config is missing required configs",
        )

    extractor_config = ExtractorConfig.from_id_and_parent_path(
        rag_config.extractor_config_id, project.path
    )
    if extractor_config is None:
        raise HTTPException(
            status_code=404,
            detail="Extractor config not found",
        )

    chunker_config = ChunkerConfig.from_id_and_parent_path(
        rag_config.chunker_config_id, project.path
    )
    if chunker_config is None:
        raise HTTPException(
            status_code=404,
            detail="Chunker config not found",
        )

    embedding_config = EmbeddingConfig.from_id_and_parent_path(
        rag_config.embedding_config_id, project.path
    )
    if embedding_config is None:
        raise HTTPException(
            status_code=404,
            detail="Embedding config not found",
        )

    vector_store_config = VectorStoreConfig.from_id_and_parent_path(
        rag_config.vector_store_config_id, project.path
    )
    if vector_store_config is None:
        raise HTTPException(
            status_code=404,
            detail="Vector store config not found",
        )

    initial_progress = await compute_current_progress_for_rag_config(
        project, rag_config
    )

    # refactor this to use better global rate limiting / throttling
    # we currently only throttle within a single job, but here we parallelize jobs
    # which causes too many concurrent subjobs to run (e.g. PDF split up into pages, each page is extracted in parallel)
    # ollama and local providers get easily stuck depending on hardware
    extractor_concurrency = 5
    if extractor_config.model_provider_name == ModelProviderName.ollama:
        extractor_concurrency = 1

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
                    concurrency=extractor_concurrency,
                    rag_config=rag_config,
                    filesystem_cache=TemporaryFilesystemCache.shared(),
                ),
                RagChunkingStepRunner(
                    project,
                    extractor_config,
                    chunker_config,
                    concurrency=5,
                    rag_config=rag_config,
                ),
                RagEmbeddingStepRunner(
                    project,
                    extractor_config,
                    chunker_config,
                    embedding_config,
                    concurrency=5,
                    rag_config=rag_config,
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
            initial_progress=initial_progress,
        ),
    )

    return runner


def connect_document_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/documents/bulk")
    async def create_documents_bulk(
        project_id: str,
        files: Annotated[List[UploadFile] | None, File()] = None,
        names: Annotated[List[str] | None, Form()] = None,
        tags: Annotated[List[str] | None, Form()] = None,
    ) -> BulkCreateDocumentsResponse:
        project = project_from_id(project_id)

        if not files:
            raise HTTPException(
                status_code=422,
                detail="At least one file must be provided",
            )

        # If names are provided, ensure they match the number of files
        if names and len(names) != len(files):
            raise HTTPException(
                status_code=422,
                detail="Number of names must match number of files",
            )

        created_documents: List[Document] = []
        failed_files: List[str] = []

        for i, file in enumerate(files):
            try:
                if not file.filename:
                    failed_files.append(f"File at index {i}: no filename provided")
                    continue

                file_data = await file.read()

                # use provided name if there is one, otherwise use the filename
                document_name = names[i] if names and i < len(names) else file.filename

                # we cannot use content_type from UploadFile because it is not always set correctly
                # depending on the browser and the file type (for example, audio/ogg sent via Safari)
                mime_type = guess_mime_type(file.filename)

                # application/octet-stream is a catch-all for unknown mime types
                if not mime_type or mime_type == "application/octet-stream":
                    failed_files.append(
                        f"File {file.filename}: Unable to determine mime type. Ensure the file name has a valid extension."
                    )
                    continue

                kind = get_kind_from_mime_type(mime_type)
                if not kind:
                    failed_files.append(
                        f"File {file.filename}: Unsupported mime type: {mime_type}"
                    )
                    continue

                document = Document(
                    parent=project,
                    name=string_to_valid_name(document_name),
                    name_override=document_name,
                    description="",  # No description support in bulk upload
                    kind=kind,
                    tags=tags if tags else [],
                    original_file=FileInfo(
                        filename=file.filename,
                        mime_type=mime_type,
                        attachment=KilnAttachmentModel.from_data(file_data, mime_type),
                        size=len(file_data),
                    ),
                )
                document.save_to_file()
                created_documents.append(document)

            except Exception as e:
                failed_files.append(
                    f"File {file.filename if file.filename else f'at index {i!s}'}: {e!s}"
                )
                continue

        if not created_documents:
            raise HTTPException(
                status_code=422,
                detail={
                    "failed_files": failed_files,
                    "error": "No files could be processed successfully",
                },
            )

        return BulkCreateDocumentsResponse(
            created_documents=created_documents,
            failed_files=failed_files,
        )

    @app.get("/api/projects/{project_id}/documents")
    async def get_documents(
        project_id: str,
    ) -> list[Document]:
        project = project_from_id(project_id)
        return project.documents(readonly=True)

    @app.get("/api/projects/{project_id}/documents/tags")
    async def get_document_tags(
        project_id: str,
    ) -> list[str]:
        project = project_from_id(project_id)
        documents = project.documents(readonly=True)
        all_tags = set()
        for document in documents:
            if document.tags:
                all_tags.update(document.tags)
        return sorted(list(all_tags))

    @app.get("/api/projects/{project_id}/documents/tag_counts")
    async def get_document_tag_counts(project_id: str) -> dict[str, int]:
        tags_count = {}
        project = project_from_id(project_id)
        # Not particularly efficient, but projects are memory cached after first load so re-compute is fairly cheap
        # We also cache the result client side
        for document in project.documents(readonly=True):
            if document.tags:
                for tag in document.tags:
                    tags_count[tag] = tags_count.get(tag, 0) + 1
        return tags_count

    @app.get("/api/projects/{project_id}/documents/{document_id}")
    async def get_document(
        project_id: str,
        document_id: str,
    ) -> Document:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )
        return document

    @app.patch("/api/projects/{project_id}/documents/{document_id}")
    async def patch_document(
        project_id: str,
        document_id: str,
        request: PatchDocumentRequest,
    ) -> Document:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )

        if request.name_override is not None:
            if request.name_override == "":
                # revert to the original name
                document.name_override = document.original_file.filename
            else:
                document.name_override = request.name_override
        if request.description is not None:
            document.description = request.description
        if request.tags is not None:
            document.tags = request.tags

        document.save_to_file()

        return document

    @app.post("/api/projects/{project_id}/documents/edit_tags")
    async def edit_tags(
        project_id: str,
        document_ids: list[str],
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
    ) -> dict[str, bool]:
        project = project_from_id(project_id)

        # all the runs we need to tag
        doc_ids_set: set[str] = set(document_ids)
        docs_found_set: set[str] = set()

        batch_size = 500
        for i in range(0, len(document_ids), batch_size):
            # release the event loop to prevent blocking other operations for too long
            await asyncio.sleep(0)

            batch_doc_ids = document_ids[i : i + batch_size]
            batch_docs = Document.from_ids_and_parent_path(
                set(batch_doc_ids), project.path
            )
            docs_found_set.update(batch_docs.keys())

            for document in batch_docs.values():
                modified = False
                if remove_tags and any(
                    tag in (document.tags or []) for tag in remove_tags
                ):
                    document.tags = list(
                        set(
                            tag
                            for tag in (document.tags or [])
                            if tag not in remove_tags
                        )
                    )
                    modified = True
                if add_tags and any(
                    tag not in (document.tags or []) for tag in add_tags
                ):
                    document.tags = list(set((document.tags or []) + add_tags))
                    modified = True
                if modified:
                    document.save_to_file()

        # all the runs we needed to tag minus the runs we did tag
        failed_documents = list(doc_ids_set - docs_found_set)
        if failed_documents:
            raise HTTPException(
                status_code=500,
                detail={
                    "failed_documents": failed_documents,
                    "error": "Documents not found",
                },
            )
        return {"success": True}

    @app.post("/api/projects/{project_id}/create_extractor_config")
    async def create_extractor_config(
        project_id: str,
        request: CreateExtractorConfigRequest,
    ) -> ExtractorConfig:
        project = project_from_id(project_id)

        properties = request.get_properties()

        extractor_config = ExtractorConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            model_provider_name=request.model_provider_name,
            model_name=request.model_name,
            output_format=request.output_format,
            passthrough_mimetypes=request.passthrough_mimetypes,
            extractor_type=properties["extractor_type"],
            properties=request.get_properties(),
            is_archived=False,
        )
        extractor_config.save_to_file()

        return extractor_config

    @app.get("/api/projects/{project_id}/extractor_configs")
    async def get_extractor_configs(
        project_id: str,
    ) -> list[ExtractorConfig]:
        project = project_from_id(project_id)
        return project.extractor_configs(readonly=True)

    @app.get("/api/projects/{project_id}/extractor_configs/{extractor_config_id}")
    async def get_extractor_config(
        project_id: str,
        extractor_config_id: str,
    ) -> ExtractorConfig:
        project = project_from_id(project_id)
        extractor_config = ExtractorConfig.from_id_and_parent_path(
            extractor_config_id, project.path
        )
        if extractor_config is None:
            raise HTTPException(
                status_code=404,
                detail="Extractor config not found",
            )
        return extractor_config

    # JS SSE client (EventSource) doesn't work with POST requests, so we use GET, even though post would be better
    @app.get(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}/run_extractor_config"
    )
    async def run_extractor_config(
        project_id: str,
        extractor_config_id: str,
    ) -> StreamingResponse:
        # the extractor may also run as part of a RAG config run, and we cannot have concurrent runs or we risk
        # having duplicate extractions
        async with shared_async_lock_manager.acquire(
            f"docs:extract:{extractor_config_id}"
        ):
            project = project_from_id(project_id)
            extractor_config = ExtractorConfig.from_id_and_parent_path(
                extractor_config_id, project.path
            )
            if extractor_config is None:
                raise HTTPException(
                    status_code=404,
                    detail="Extractor config not found",
                )

            if extractor_config.is_archived:
                raise HTTPException(
                    status_code=422,
                    detail="Extractor config is archived. You must unarchive it to use it.",
                )

            documents = project.documents(readonly=True)

            extractor_runner = ExtractorRunner(
                extractor_configs=[extractor_config],
                documents=documents,
            )

            return await run_extractor_runner_with_status(extractor_runner)

    @app.get("/api/projects/{project_id}/documents/{document_id}/extractions")
    async def get_extractions(
        project_id: str,
        document_id: str,
    ) -> list[ExtractionSummary]:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )

        summaries: list[ExtractionSummary] = []
        for extraction in document.extractions(readonly=True):
            extractor_config = ExtractorConfig.from_id_and_parent_path(
                str(extraction.extractor_config_id), project.path
            )

            if not extractor_config:
                continue

            summaries.append(
                build_extraction_summary(
                    extraction=extraction,
                    output_content=await extraction.output_content() or "",
                    extractor_config=extractor_config,
                )
            )

        return summaries

    @app.get(
        "/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}"
    )
    async def get_extraction(
        project_id: str,
        document_id: str,
        extraction_id: str,
    ) -> ExtractionSummary:
        project = project_from_id(project_id)

        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )

        extraction = Extraction.from_id_and_parent_path(extraction_id, document.path)
        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction {extraction_id} not found",
            )

        extractor_config = ExtractorConfig.from_id_and_parent_path(
            str(extraction.extractor_config_id), project.path
        )
        if not extractor_config:
            raise HTTPException(
                status_code=404,
                detail=f"Extractor config {extraction.extractor_config_id} not found",
            )

        return build_extraction_summary(
            extraction=extraction,
            output_content=await extraction.output_content() or "",
            extractor_config=extractor_config,
        )

    @app.get("/api/projects/{project_id}/documents/{document_id}/download")
    async def download_document_file(
        project_id: str,
        document_id: str,
    ) -> FileResponse:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )
        if not document.path:
            raise HTTPException(
                status_code=500,
                detail="Document path not found",
            )

        path = document.original_file.attachment.resolve_path(
            document.path.parent
        ).resolve()

        return FileResponse(path=path, filename=document.original_file.filename)

    @app.post(
        "/api/projects/{project_id}/documents/{document_id}/open_enclosing_folder"
    )
    async def open_document_enclosing_folder(
        project_id: str,
        document_id: str,
    ) -> OpenFileResponse:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)

        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )

        if not document.path:
            raise HTTPException(
                status_code=500,
                detail="Document path not found",
            )

        open_folder(document.path)

        return OpenFileResponse(path=str(document.path.parent))

    @app.post("/api/projects/{project_id}/documents/delete")
    async def delete_documents(project_id: str, document_ids: list[str]) -> dict:
        project = project_from_id(project_id)
        for document_id in document_ids:
            document = Document.from_id_and_parent_path(document_id, project.path)
            if not document:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document {document_id} not found",
                )

            document.delete()

        return {"message": f"Documents removed. IDs: {document_ids}"}

    @app.delete("/api/projects/{project_id}/documents/{document_id}")
    async def delete_document(project_id: str, document_id: str) -> dict:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )

        document.delete()

        return {"message": f"Document removed. ID: {document_id}"}

    @app.get(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}/progress"
    )
    async def get_extraction_progress(
        project_id: str,
        extractor_config_id: str,
    ) -> ExtractionProgress:
        project = project_from_id(project_id)
        extractor_config = ExtractorConfig.from_id_and_parent_path(
            extractor_config_id, project.path
        )
        if extractor_config is None:
            raise HTTPException(
                status_code=404,
                detail="Extractor config not found",
            )

        documents = project.documents(readonly=True)

        document_count_successful = 0
        for document in documents:
            extractions = document.extractions(readonly=True)
            if any(
                extraction.extractor_config_id == extractor_config_id
                for extraction in extractions
            ):
                document_count_successful += 1

        return ExtractionProgress(
            document_count_total=len(documents),
            document_count_successful=document_count_successful,
            extractor_config=extractor_config,
        )

    @app.post("/api/projects/{project_id}/documents/{document_id}/extract")
    async def extract_file(
        project_id: str,
        document_id: str,
        extractor_config_ids: list[ID_TYPE] | None = None,
    ) -> StreamingResponse:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )

        if extractor_config_ids is None:
            extractor_config_ids = [
                extractor_config.id
                for extractor_config in [
                    ec
                    for ec in project.extractor_configs(readonly=True)
                    if not ec.is_archived
                ]
                if not extractor_config.is_archived
            ]

        extractor_configs: list[ExtractorConfig] = []
        for extractor_config_id in extractor_config_ids:
            extractor_config = ExtractorConfig.from_id_and_parent_path(
                str(extractor_config_id), project.path
            )
            if extractor_config is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Extractor config {extractor_config_id} not found",
                )
            extractor_configs.append(extractor_config)

        extractor_runner = ExtractorRunner(
            extractor_configs=extractor_configs,
            documents=[document],
        )

        return await run_extractor_runner_with_status(extractor_runner)

    @app.delete(
        "/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}"
    )
    async def delete_extraction(
        project_id: str,
        document_id: str,
        extraction_id: str,
    ) -> dict:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
            )

        # should not happen
        if document.path is None:
            raise HTTPException(
                status_code=500,
                detail="Document path not found",
            )

        extraction = Extraction.from_id_and_parent_path(extraction_id, document.path)
        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction {extraction_id} not found",
            )
        extraction.delete()

        if extraction.extractor_config_id is None:
            raise HTTPException(
                status_code=404,
                detail="Extractor config ID not found",
            )

        # there may be some cached partial extraction data in cache, which would be picked
        # up on the next extraction run for this file, so we need to clear it
        extractor_config = ExtractorConfig.from_id_and_parent_path(
            extraction.extractor_config_id, project.path
        )
        if extractor_config is None:
            raise HTTPException(
                status_code=404,
                detail="Extractor config not found",
            )

        extractor = extractor_adapter_from_type(
            extractor_config.extractor_type,
            extractor_config,
            filesystem_cache=TemporaryFilesystemCache.shared(),
        )

        try:
            await extractor.clear_cache_for_file_path(
                document.original_file.attachment.resolve_path(document.path.parent)
            )
        except Exception as e:
            logger.warning(
                "Failed to clear extractor cache for document %s (extraction %s): %s",
                document_id,
                extraction_id,
                e,
                exc_info=True,
            )

        return {"message": f"Extraction removed. ID: {extraction_id}"}

    @app.patch("/api/projects/{project_id}/extractor_configs/{extractor_config_id}")
    async def patch_extractor_config(
        project_id: str,
        extractor_config_id: str,
        request: PatchExtractorConfigRequest,
    ) -> dict:
        project = project_from_id(project_id)
        extractor_config = ExtractorConfig.from_id_and_parent_path(
            extractor_config_id, project.path
        )

        if extractor_config is None:
            raise HTTPException(
                status_code=404,
                detail="Extractor config not found",
            )

        if request.name is not None:
            extractor_config.name = request.name
        if request.description is not None:
            extractor_config.description = request.description
        if request.is_archived is not None:
            extractor_config.is_archived = request.is_archived

        extractor_config.save_to_file()

        return {"message": f"Extractor config updated. ID: {extractor_config_id}"}

    @app.post("/api/projects/{project_id}/create_chunker_config")
    async def create_chunker_config(
        project_id: str,
        request: CreateChunkerConfigRequest,
    ) -> ChunkerConfig:
        project = project_from_id(project_id)

        # if semantic, validate that the referenced embedding config exists
        if request.properties.chunker_type == ChunkerType.SEMANTIC:
            embedding_config = EmbeddingConfig.from_id_and_parent_path(
                request.properties.embedding_config_id, project.path
            )
            if not embedding_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Embedding config {request.properties.embedding_config_id} not found",
                )

        chunker_config = ChunkerConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            chunker_type=request.chunker_type,
            properties=request.get_properties_for_chunker_type(),
        )
        chunker_config.save_to_file()

        return chunker_config

    @app.get("/api/projects/{project_id}/chunker_configs")
    async def get_chunker_configs(
        project_id: str,
    ) -> list[ChunkerConfig]:
        project = project_from_id(project_id)
        return project.chunker_configs(readonly=True)

    @app.post("/api/projects/{project_id}/create_embedding_config")
    async def create_embedding_config(
        project_id: str,
        request: CreateEmbeddingConfigRequest,
    ) -> EmbeddingConfig:
        project = project_from_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found",
            )

        embedding_config = EmbeddingConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            model_provider_name=request.model_provider_name,
            model_name=request.model_name,
            properties=request.properties,
        )
        embedding_config.save_to_file()

        return embedding_config

    @app.get("/api/projects/{project_id}/embedding_configs")
    async def get_embedding_configs(
        project_id: str,
    ) -> list[EmbeddingConfig]:
        project = project_from_id(project_id)
        return project.embedding_configs(readonly=True)

    @app.post("/api/projects/{project_id}/create_reranker_config")
    async def create_reranker_config(
        project_id: str,
        request: CreateRerankerConfigRequest,
    ) -> RerankerConfig:
        project = project_from_id(project_id)

        reranker_config = RerankerConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            top_n=request.top_n,
            model_provider_name=request.model_provider_name,
            model_name=request.model_name,
            properties=request.get_reranker_config_properties(),
        )
        reranker_config.save_to_file()

        return reranker_config

    @app.get("/api/projects/{project_id}/reranker_configs")
    async def get_reranker_configs(
        project_id: str,
    ) -> list[RerankerConfig]:
        project = project_from_id(project_id)
        return project.reranker_configs(readonly=True)

    @app.get("/api/projects/{project_id}/embedding_configs/{embedding_config_id}")
    async def get_embedding_config(
        project_id: str,
        embedding_config_id: str,
    ) -> EmbeddingConfig:
        project = project_from_id(project_id)
        embedding_config = EmbeddingConfig.from_id_and_parent_path(
            embedding_config_id, project.path
        )
        if embedding_config is None:
            raise HTTPException(
                status_code=404,
                detail=f"Embedding config {embedding_config_id} not found",
            )
        return embedding_config

    @app.post("/api/projects/{project_id}/create_vector_store_config")
    async def create_vector_store_config(
        project_id: str,
        request: CreateVectorStoreConfigRequest,
    ) -> VectorStoreConfig:
        project = project_from_id(project_id)
        vector_store_config = VectorStoreConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            store_type=request.store_type,
            properties=request.get_properties_for_store_type(),
        )
        vector_store_config.save_to_file()

        return vector_store_config

    @app.get("/api/projects/{project_id}/vector_store_configs")
    async def get_vector_store_configs(
        project_id: str,
    ) -> list[VectorStoreConfig]:
        project = project_from_id(project_id)
        return project.vector_store_configs(readonly=True)

    @app.patch("/api/projects/{project_id}/rag_configs/{rag_config_id}")
    async def update_rag_config(
        project_id: str, rag_config_id: str, request: UpdateRagConfigRequest
    ) -> RagConfig:
        project = project_from_id(project_id)
        rag_config = get_rag_config_from_id(project, rag_config_id)
        if request.name is not None:
            rag_config.name = request.name
        if request.description is not None:
            rag_config.description = request.description
        if request.is_archived is not None:
            rag_config.is_archived = request.is_archived
        rag_config.save_to_file()
        return rag_config

    @app.post("/api/projects/{project_id}/rag_configs/create_rag_config")
    async def create_rag_config(
        project_id: str,
        request: CreateRagConfigRequest,
    ) -> RagConfig:
        project = project_from_id(project_id)

        # check that the extractor, chunker, and embedding configs exist
        extractor_config = ExtractorConfig.from_id_and_parent_path(
            str(request.extractor_config_id), project.path
        )
        if not extractor_config:
            raise HTTPException(
                status_code=404,
                detail=f"Extractor config {request.extractor_config_id} not found",
            )
        chunker_config = ChunkerConfig.from_id_and_parent_path(
            str(request.chunker_config_id), project.path
        )
        if not chunker_config:
            raise HTTPException(
                status_code=404,
                detail=f"Chunker config {request.chunker_config_id} not found",
            )
        embedding_config = EmbeddingConfig.from_id_and_parent_path(
            str(request.embedding_config_id), project.path
        )
        if not embedding_config:
            raise HTTPException(
                status_code=404,
                detail=f"Embedding config {request.embedding_config_id} not found",
            )

        vector_store_config = VectorStoreConfig.from_id_and_parent_path(
            str(request.vector_store_config_id), project.path
        )
        if not vector_store_config:
            raise HTTPException(
                status_code=404,
                detail=f"Vector store config {request.vector_store_config_id} not found",
            )

        reranker_config = None
        has_reranker = request.reranker_config_id is not None
        if has_reranker:
            reranker_config = RerankerConfig.from_id_and_parent_path(
                str(request.reranker_config_id), project.path
            )
            if not reranker_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Reranker config {request.reranker_config_id} not found",
                )

        rag_config = RagConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            tool_name=request.tool_name,
            tool_description=request.tool_description,
            extractor_config_id=extractor_config.id,
            chunker_config_id=chunker_config.id,
            embedding_config_id=embedding_config.id,
            vector_store_config_id=vector_store_config.id,
            reranker_config_id=reranker_config.id if reranker_config else None,
            tags=request.tags,
        )
        rag_config.save_to_file()

        return rag_config

    @app.get("/api/projects/{project_id}/rag_configs")
    async def get_rag_configs(
        project_id: str,
    ) -> list[RagConfigWithSubConfigs]:
        project = project_from_id(project_id)

        rag_configs: list[RagConfigWithSubConfigs] = []
        for rag_config in project.rag_configs(readonly=True):
            extractor_config = ExtractorConfig.from_id_and_parent_path(
                str(rag_config.extractor_config_id), project.path
            )
            if not extractor_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Extractor config {rag_config.extractor_config_id} not found",
                )

            chunker_config = ChunkerConfig.from_id_and_parent_path(
                str(rag_config.chunker_config_id), project.path
            )
            if not chunker_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Chunker config {rag_config.chunker_config_id} not found",
                )

            embedding_config = EmbeddingConfig.from_id_and_parent_path(
                str(rag_config.embedding_config_id), project.path
            )
            if not embedding_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Embedding config {rag_config.embedding_config_id} not found",
                )

            vector_store_config = VectorStoreConfig.from_id_and_parent_path(
                str(rag_config.vector_store_config_id), project.path
            )
            if not vector_store_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Vector store config {rag_config.vector_store_config_id} not found",
                )

            reranker_config = None
            has_reranker = rag_config.reranker_config_id is not None
            if has_reranker:
                reranker_config = RerankerConfig.from_id_and_parent_path(
                    str(rag_config.reranker_config_id), project.path
                )
                if not reranker_config:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Reranker config {rag_config.reranker_config_id} not found",
                    )

            rag_configs.append(
                RagConfigWithSubConfigs(
                    id=rag_config.id,
                    name=rag_config.name,
                    description=rag_config.description,
                    tool_name=rag_config.tool_name,
                    tool_description=rag_config.tool_description,
                    tags=rag_config.tags,
                    created_at=rag_config.created_at,
                    created_by=rag_config.created_by,
                    is_archived=rag_config.is_archived,
                    extractor_config=extractor_config,
                    chunker_config=chunker_config,
                    embedding_config=embedding_config,
                    vector_store_config=vector_store_config,
                    reranker_config=reranker_config,
                )
            )

        return rag_configs

    @app.get("/api/projects/{project_id}/rag_configs/{rag_config_id}")
    async def get_rag_config(
        project_id: str,
        rag_config_id: str,
    ) -> RagConfigWithSubConfigs:
        project = project_from_id(project_id)
        rag_config = get_rag_config_from_id(project, rag_config_id)
        extractor_config = ExtractorConfig.from_id_and_parent_path(
            str(rag_config.extractor_config_id), project.path
        )
        if not extractor_config:
            raise HTTPException(
                status_code=404,
                detail=f"Extractor config {rag_config.extractor_config_id} not found",
            )

        chunker_config = ChunkerConfig.from_id_and_parent_path(
            str(rag_config.chunker_config_id), project.path
        )
        if not chunker_config:
            raise HTTPException(
                status_code=404,
                detail=f"Chunker config {rag_config.chunker_config_id} not found",
            )

        embedding_config = EmbeddingConfig.from_id_and_parent_path(
            str(rag_config.embedding_config_id), project.path
        )
        if not embedding_config:
            raise HTTPException(
                status_code=404,
                detail=f"Embedding config {rag_config.embedding_config_id} not found",
            )

        vector_store_config = VectorStoreConfig.from_id_and_parent_path(
            str(rag_config.vector_store_config_id), project.path
        )
        if not vector_store_config:
            raise HTTPException(
                status_code=404,
                detail=f"Vector store config {rag_config.vector_store_config_id} not found",
            )

        reranker_config = None
        has_reranker = rag_config.reranker_config_id is not None
        if has_reranker:
            reranker_config = RerankerConfig.from_id_and_parent_path(
                str(rag_config.reranker_config_id), project.path
            )
            if not reranker_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Reranker config {rag_config.reranker_config_id} not found",
                )

        return RagConfigWithSubConfigs(
            id=rag_config.id,
            name=rag_config.name,
            description=rag_config.description,
            tool_name=rag_config.tool_name,
            tool_description=rag_config.tool_description,
            created_at=rag_config.created_at,
            created_by=rag_config.created_by,
            is_archived=rag_config.is_archived,
            extractor_config=extractor_config,
            chunker_config=chunker_config,
            embedding_config=embedding_config,
            vector_store_config=vector_store_config,
            reranker_config=reranker_config,
            tags=rag_config.tags,
        )

    # JS SSE client (EventSource) doesn't work with POST requests, so we use GET, even though post would be better
    @app.get("/api/projects/{project_id}/rag_configs/{rag_config_id}/run")
    async def run_rag_config(
        project_id: str,
        rag_config_id: str,
    ) -> StreamingResponse:
        project = project_from_id(project_id)

        rag_config = get_rag_config_from_id(project, rag_config_id)
        if rag_config.is_archived:
            raise HTTPException(
                status_code=422,
                detail="This RAG configuration is archived. You must unarchive it to use it.",
            )

        async def runner_factory():
            return await build_rag_workflow_runner(project, rag_config_id)

        # the workflow runner handles locking
        return await run_rag_workflow_runner_with_status(runner_factory)

    @app.post("/api/projects/{project_id}/rag_configs/progress")
    async def get_rag_config_progress(
        project_id: str,
        request: GetRagConfigProgressRequest,
    ) -> Dict[str, RagProgress]:
        project = project_from_id(project_id)
        rag_configs: list[RagConfig] = []

        if request.rag_config_ids:
            for rag_config_id in request.rag_config_ids:
                rag_config = RagConfig.from_id_and_parent_path(
                    rag_config_id, project.path
                )
                if rag_config is None:
                    continue
                rag_configs.append(rag_config)

            if not rag_configs:
                return {}
        else:
            rag_configs = project.rag_configs(readonly=True)

        progress_map: Dict[
            str, RagProgress
        ] = await compute_current_progress_for_rag_configs(project, rag_configs)
        return progress_map

    @app.post("/api/projects/{project_id}/rag_configs/{rag_config_id}/search")
    async def search_rag_config(
        project_id: str,
        rag_config_id: str,
        request: RagSearchRequest,
    ) -> RagSearchResponse:
        """Search the vector store associated with a RAG config."""
        project = project_from_id(project_id)

        # Get the RAG config and associated configs
        rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
        if rag_config is None:
            raise HTTPException(
                status_code=404,
                detail="RAG config not found",
            )

        if rag_config.is_archived:
            raise HTTPException(
                status_code=422,
                detail="This RAG configuration is archived. You must unarchive it to use it.",
            )

        # Empty query - return empty results
        if not request.query.strip():
            return RagSearchResponse(results=[])

        # Get the vector store config
        vector_store_config = VectorStoreConfig.from_id_and_parent_path(
            str(rag_config.vector_store_config_id), project.path
        )
        if vector_store_config is None:
            raise HTTPException(
                status_code=404,
                detail="Vector store config not found",
            )

        # Get the embedding config
        embedding_config = EmbeddingConfig.from_id_and_parent_path(
            str(rag_config.embedding_config_id), project.path
        )
        if not embedding_config:
            raise HTTPException(
                status_code=404,
                detail="Embedding config not found",
            )

        # Create the vector store adapter
        vector_store_adapter = await vector_store_adapter_for_config(
            rag_config, vector_store_config
        )

        # Prepare the search query based on vector store type
        search_query: VectorStoreQuery

        if vector_store_config.store_type == VectorStoreType.LANCE_DB_FTS:
            # For FTS, just use the text query
            search_query = VectorStoreQuery(
                query_string=request.query,
                query_embedding=None,
            )
        elif vector_store_config.store_type in [
            VectorStoreType.LANCE_DB_VECTOR,
            VectorStoreType.LANCE_DB_HYBRID,
        ]:
            # For vector and hybrid search, generate embeddings for the query
            embedding_adapter = embedding_adapter_from_type(embedding_config)
            embedding_result = await embedding_adapter.generate_embeddings(
                [request.query]
            )

            if not embedding_result.embeddings:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate embeddings for search query",
                )

            query_embedding = embedding_result.embeddings[0].vector

            if vector_store_config.store_type == VectorStoreType.LANCE_DB_VECTOR:
                # Pure vector search
                search_query = VectorStoreQuery(
                    query_string=None,
                    query_embedding=query_embedding,
                )
            else:
                # Hybrid search
                search_query = VectorStoreQuery(
                    query_string=request.query,
                    query_embedding=query_embedding,
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported vector store type: {vector_store_config.store_type}",
            )

        # Perform the search
        try:
            search_results = await vector_store_adapter.search(search_query)
            return RagSearchResponse(results=search_results)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Search failed: {e!s}",
            )
