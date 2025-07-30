import asyncio
import datetime
import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from kiln_ai.adapters.extractors.extractor_runner import ExtractorRunner
from kiln_ai.adapters.ml_embedding_model_list import EmbeddingModelName
from kiln_ai.adapters.ml_model_list import built_in_models_from_provider
from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    NAME_REGEX,
    KilnAttachmentModel,
    string_to_valid_name,
)
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractorConfig,
    ExtractorType,
    FileInfo,
    OutputFormat,
    get_kind_from_mime_type,
)
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.utils.document_pipeline import (
    DocumentPipeline,
    DocumentPipelineConfiguration,
)
from kiln_ai.utils.mime_type import guess_mime_type
from kiln_ai.utils.name_generator import generate_memorable_name
from pydantic import BaseModel, Field, model_validator

from kiln_server.project_api import project_from_id

logger = logging.getLogger(__name__)

# keep track of locks by extractor config ID to prevent concurrent runs of the same extractor config
# maps from extractor config ID -> lock
run_extractor_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


# keep track of locks by rag config ID to prevent concurrent runs of the same rag config
# maps from rag config ID -> lock
run_rag_config_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def open_folder(path: str | Path) -> None:
    if sys.platform.startswith("darwin"):
        subprocess.run(["open", path], check=True)
    elif sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", path], check=True)


# TODO: extract out into common utils
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


class OpenFileResponse(BaseModel):
    path: str


class DiscoverServeFileResponse(BaseModel):
    url: str


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


class RagProgress(BaseModel):
    # total counts
    total_document_count: int
    total_document_completed_count: int
    total_document_extracted_count: int
    total_document_chunked_count: int
    total_document_embedded_count: int


class DocumentWiseProgress(BaseModel):
    extracted: bool
    chunked: bool
    embedded: bool


class CreateRagConfigRequest(BaseModel):
    name: str | None = Field(
        description="A name for this entity.",
        min_length=1,
        max_length=120,
        pattern=NAME_REGEX,
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="The description of the document pipeline",
        default=None,
    )
    extractor_config_id: ID_TYPE = Field(
        description="The extractor config to use for the document pipeline",
    )
    chunker_config_id: ID_TYPE = Field(
        description="The chunker config to use for the document pipeline",
    )
    embedding_config_id: ID_TYPE = Field(
        description="The embedding config to use for the document pipeline",
    )


class CreateChunkerConfigRequest(BaseModel):
    name: str | None = Field(
        description="A name for this entity.",
        min_length=1,
        max_length=120,
        pattern=NAME_REGEX,
        default_factory=generate_memorable_name,
    )
    description: str | None = Field(
        description="The description of the chunker config",
        default=None,
    )
    chunker_type: ChunkerType = Field(
        description="The type of the chunker",
    )
    properties: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
    )


class CreateEmbeddingConfigRequest(BaseModel):
    name: str | None = Field(
        description="A name for this entity.",
        min_length=1,
        max_length=120,
        pattern=NAME_REGEX,
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
    properties: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
    )


class CreateExtractorConfigRequest(BaseModel):
    # FIXME: should use the centralized field for name, but the openapi codegen
    # does not infer correctly that the field is optional when using the centralized
    # field for name
    name: str | None = Field(
        description="A name for this entity.",
        min_length=1,
        max_length=120,
        pattern=NAME_REGEX,
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
    properties: dict[str, str | int | float | bool | dict[str, str] | None] = Field(
        default_factory=dict,
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
            raise ValueError(
                f"Model {self.model_name} not found in {self.model_provider_name}"
            )

        if not model.supports_doc_extraction:
            raise ValueError(
                f"Model {self.model_name} does not support document extraction"
            )

        return self


class PatchExtractorConfigRequest(BaseModel):
    # FIXME: should use the centralized field for name, but the openapi codegen
    # does not infer correctly that the field is optional when using the centralized
    # field for name
    name: str | None = Field(
        description="A name for this entity.",
        min_length=1,
        max_length=120,
        pattern=NAME_REGEX,
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
    rag_config_ids: list[str]


def connect_document_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/documents")
    async def create_document(
        project_id: str,
        file: UploadFile = File(...),
        name: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
    ) -> Document:
        file_data = await file.read()
        project = project_from_id(project_id)

        if not file.filename:
            raise HTTPException(
                status_code=422,
                detail="File must have a filename",
            )

        # we cannot use content_type from UploadFile because it is not always set correctly
        # depending on the browser and the file type (for example, audio/ogg sent via Safari)
        mime_type = guess_mime_type(file.filename)

        # application/octet-stream is a catch-all for unknown mime types
        if not mime_type or mime_type == "application/octet-stream":
            raise HTTPException(
                status_code=422,
                detail=f"Unable to determine mime type for {file.filename}. Ensure the file name has a valid extension.",
            )

        kind = get_kind_from_mime_type(mime_type)
        if not kind:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported mime type: {mime_type} for file {file.filename}",
            )

        document = Document(
            parent=project,
            name=string_to_valid_name(name or file.filename),
            description=description,
            kind=kind,
            original_file=FileInfo(
                filename=file.filename,
                mime_type=mime_type,
                attachment=KilnAttachmentModel.from_data(file_data, mime_type),
                size=len(file_data),
            ),
        )
        document.save_to_file()

        for extractor_config in [
            ec for ec in project.extractor_configs(readonly=True) if not ec.is_archived
        ]:
            extractor_runner = ExtractorRunner(
                extractor_configs=[extractor_config],
                documents=[document],
            )
            async for progress in extractor_runner.run():
                pass

        return document

    @app.get("/api/projects/{project_id}/documents")
    async def get_documents(
        project_id: str,
    ) -> list[Document]:
        project = project_from_id(project_id)
        return project.documents(readonly=True)

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

    @app.post("/api/projects/{project_id}/documents/edit_tags")
    async def edit_tags(
        project_id: str,
        document_ids: list[str],
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
    ) -> dict[str, bool]:
        project = project_from_id(project_id)
        failed_documents: list[str] = []
        for document_id in document_ids:
            document = Document.from_id_and_parent_path(document_id, project.path)
            if not document:
                failed_documents.append(document_id)
            else:
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

        extractor_config = ExtractorConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            model_provider_name=request.model_provider_name,
            model_name=request.model_name,
            output_format=request.output_format,
            passthrough_mimetypes=request.passthrough_mimetypes,
            extractor_type=ExtractorType.LITELLM,
            properties=request.properties,
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
        async with run_extractor_locks[extractor_config_id]:
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

        open_folder(document.path.parent)

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

        extraction = Extraction.from_id_and_parent_path(extraction_id, document.path)
        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction {extraction_id} not found",
            )

        extraction.delete()

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

        chunker_config = ChunkerConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            chunker_type=request.chunker_type,
            properties=request.properties,
        )
        chunker_config.save_to_file()

        return chunker_config

    @app.get("/api/projects/{project_id}/chunker_configs")
    async def get_chunker_configs(
        project_id: str,
    ) -> list[ChunkerConfig]:
        project = project_from_id(project_id)
        return project.chunker_configs(readonly=True)

    @app.get("/api/projects/{project_id}/chunker_configs/{chunker_config_id}")
    async def get_chunker_config(
        project_id: str,
        chunker_config_id: str,
    ) -> ChunkerConfig:
        project = project_from_id(project_id)
        chunker_config = ChunkerConfig.from_id_and_parent_path(
            chunker_config_id, project.path
        )
        if chunker_config is None:
            raise HTTPException(
                status_code=404,
                detail="Chunker config not found",
            )

        return chunker_config

    @app.post("/api/projects/{project_id}/create_embedding_config")
    async def create_embedding_config(
        project_id: str,
        request: CreateEmbeddingConfigRequest,
    ) -> EmbeddingConfig:
        project = project_from_id(project_id)

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
                detail="Embedding config not found",
            )
        return embedding_config

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

        rag_config = RagConfig(
            parent=project,
            name=string_to_valid_name(request.name or generate_memorable_name()),
            description=request.description,
            extractor_config_id=extractor_config.id,
            chunker_config_id=chunker_config.id,
            embedding_config_id=embedding_config.id,
        )
        rag_config.save_to_file()

        return rag_config

    @app.get("/api/projects/{project_id}/rag_configs")
    async def get_rag_configs(
        project_id: str,
    ) -> list[RagConfig]:
        project = project_from_id(project_id)
        return project.rag_configs(readonly=True)

    @app.get("/api/projects/{project_id}/rag_configs/{rag_config_id}")
    async def get_rag_config(
        project_id: str,
        rag_config_id: str,
    ) -> RagConfig:
        project = project_from_id(project_id)
        rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
        if rag_config is None:
            raise HTTPException(
                status_code=404,
                detail="RAG config not found",
            )
        return rag_config

    @app.post("/api/projects/{project_id}/rag_configs/{rag_config_id}/run")
    async def run_rag_config(
        project_id: str,
        rag_config_id: str,
    ) -> dict:
        # prevent concurrent runs of the same rag config that would result in duplicates
        async with run_rag_config_locks[rag_config_id]:
            project = project_from_id(project_id)
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

            pipeline = DocumentPipeline(
                project,
                DocumentPipelineConfiguration(
                    rag_config=rag_config,
                    extractor_config=extractor_config,
                    chunker_config=chunker_config,
                    embedding_config=embedding_config,
                ),
            )
            await pipeline.run()

            return {"message": f"RAG config {rag_config_id} run started"}

    @app.post("/api/projects/{project_id}/rag_configs/progress")
    async def get_rag_config_progress(
        project_id: str,
        request: GetRagConfigProgressRequest,
    ) -> dict[str, RagProgress]:
        project = project_from_id(project_id)
        rag_configs: list[RagConfig] = []

        # not a big deal if some of the configs are not found, we'll just ignore them - better
        # than throwing because of a potential delete happening concurrently since progress does
        # not require integrity
        for rag_config_id in request.rag_config_ids:
            rag_config = RagConfig.from_id_and_parent_path(rag_config_id, project.path)
            if rag_config is None:
                continue
            rag_configs.append(rag_config)

        # no configs found, nothing to return
        if not rag_configs:
            return {}

        # a rag config is a unique path through the filesystem tree
        # we serialize each path as node_name::node_name::...::node_name
        # and store the path -> [rag config ids] for each level in the tree
        # so we can easily look up what rag configs we are at without
        # always needing to check all the loops combined state
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

        rag_config_progress_map: dict[str, RagProgress] = defaultdict(
            lambda: RagProgress(
                total_document_count=0,
                total_document_completed_count=0,
                total_document_extracted_count=0,
                total_document_chunked_count=0,
                total_document_embedded_count=0,
            )
        )
        for document in project.documents(readonly=True):
            # for typechecker - should not actually happen
            if not document.id:
                raise ValueError(f"Document {document.path} has no ID")

            for rag_config in rag_configs:
                rag_config_progress_map[str(rag_config.id)].total_document_count += 1

            for extraction in document.extractions(readonly=True):
                # update progress for all the configs that descend from this path
                extraction_path_prefix = str(extraction.extractor_config_id)
                for matching_rag_config_id in path_prefixes[extraction_path_prefix]:
                    rag_config_progress_map[
                        matching_rag_config_id
                    ].total_document_extracted_count += 1

                for chunked_document in extraction.chunked_documents(readonly=True):
                    chunking_path_prefix = f"{extraction_path_prefix}::{chunked_document.chunker_config_id}"
                    for matching_rag_config_id in path_prefixes[chunking_path_prefix]:
                        rag_config_progress_map[
                            matching_rag_config_id
                        ].total_document_chunked_count += 1

                    for embedding in chunked_document.chunk_embeddings(readonly=True):
                        embedding_path_prefix = (
                            f"{chunking_path_prefix}::{embedding.embedding_config_id}"
                        )
                        for matching_rag_config_id in path_prefixes[
                            embedding_path_prefix
                        ]:
                            rag_config_progress_map[
                                matching_rag_config_id
                            ].total_document_embedded_count += 1

        # if any step fails, then the document is not considered completed, so it follows
        # that the number of completed documents can only be as large as the minimum of the
        # completion counts for each step
        for rag_config_id, rag_config_progress in rag_config_progress_map.items():
            rag_config_progress.total_document_completed_count = min(
                rag_config_progress.total_document_extracted_count,
                rag_config_progress.total_document_chunked_count,
                rag_config_progress.total_document_embedded_count,
            )

        return dict(rag_config_progress_map)
