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
from kiln_ai.adapters.extractors.extraction_prompt_builder import (
    ExtractionPromptBuilder,
)
from kiln_ai.adapters.extractors.extractor_runner import ExtractorRunner
from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    KilnAttachmentModel,
    string_to_valid_name,
)
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractorConfig,
    ExtractorType,
    FileInfo,
    Kind,
    OutputFormat,
)
from kiln_ai.utils.name_generator import generate_memorable_name
from pydantic import BaseModel, Field, model_validator

from kiln_server.project_api import project_from_id

logger = logging.getLogger(__name__)

# keep track of locks by extractor config ID to prevent concurrent runs of the same extractor config
# maps from extractor config ID -> lock
run_extractor_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


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
    current_extractor_config: ExtractorConfig | None


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
    extractor_config_id: str
    output_content: str
    extractor: ExtractorSummary


class CreateExtractorConfigRequest(BaseModel):
    name: str | None = Field(
        description="The name of the extractor config",
        default=None,
    )
    description: str | None = Field(
        description="The description of the extractor config",
        default=None,
    )
    output_format: OutputFormat = Field(
        description="The output format of the extractor config",
    )
    passthrough_mimetypes: list[OutputFormat] = Field(
        description="The mimetypes to pass through to the extractor",
        default_factory=list,
    )
    extractor_type: ExtractorType = Field(
        description="The type of the extractor",
    )
    properties: dict[str, str | int | float | bool | dict[str, str] | None] = Field(
        default={},
    )

    @model_validator(mode="before")
    def set_default_name(cls, values: dict) -> dict:
        if values.get("name") is None:
            values["name"] = generate_memorable_name()
        else:
            values["name"] = string_to_valid_name(values["name"])
        return values

    @model_validator(mode="after")
    def set_default_properties(self):
        if not isinstance(self.properties, dict):
            raise ValueError("Properties must be a dictionary")

        match self.extractor_type:
            case ExtractorType.GEMINI:
                self.properties = gemini_properties_with_defaults(self)
            case _:
                pass

        return self


def gemini_properties_with_defaults(
    request: CreateExtractorConfigRequest,
) -> dict[str, str | int | float | bool | dict[str, str] | None]:
    def with_default(key: str, default: str) -> str:
        value = request.properties.get(key)
        if value is None or value == "":
            return default
        if not isinstance(value, str):
            raise ValueError(f"Prompt for {key} must be a string")
        return value

    return {
        "model_name": with_default("model_name", ""),
        "prompt_document": with_default(
            "prompt_document",
            ExtractionPromptBuilder.prompt_for_kind(
                kind=Kind.DOCUMENT, output_format=request.output_format
            ),
        ),
        "prompt_image": with_default(
            "prompt_image",
            ExtractionPromptBuilder.prompt_for_kind(
                kind=Kind.IMAGE, output_format=request.output_format
            ),
        ),
        "prompt_video": with_default(
            "prompt_video",
            ExtractionPromptBuilder.prompt_for_kind(
                kind=Kind.VIDEO, output_format=request.output_format
            ),
        ),
        "prompt_audio": with_default(
            "prompt_audio",
            ExtractionPromptBuilder.prompt_for_kind(
                kind=Kind.AUDIO, output_format=request.output_format
            ),
        ),
    }


class PatchExtractorConfigRequest(BaseModel):
    name: str | None = Field(
        description="The name of the extractor config",
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
        content_type = file.content_type or ""
        if content_type.startswith("image/"):
            kind = Kind.IMAGE
        elif content_type.startswith("video/"):
            kind = Kind.VIDEO
        elif content_type.startswith("audio/"):
            kind = Kind.AUDIO
        else:
            kind = Kind.DOCUMENT

        document = Document(
            parent=project,
            name=string_to_valid_name(name),
            description=description,
            kind=kind,
            original_file=FileInfo(
                filename=file.filename or "",
                mime_type=content_type,
                attachment=KilnAttachmentModel.from_data(file_data, content_type),
                size=len(file_data),
            ),
        )
        document.save_to_file()

        for extractor_config in [
            ec for ec in project.extractor_configs() if not ec.is_archived
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

        # NOTE: maybe add cache here (readonly=True flag)?
        return project.documents()

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
            output_format=request.output_format,
            passthrough_mimetypes=request.passthrough_mimetypes,
            extractor_type=request.extractor_type,
            properties=request.properties,
        )
        extractor_config.save_to_file()

        return extractor_config

    @app.get("/api/projects/{project_id}/extractor_configs")
    async def get_extractor_configs(
        project_id: str,
    ) -> list[ExtractorConfig]:
        project = project_from_id(project_id)
        return project.extractor_configs()

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

            documents = project.documents()

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

        extractor_configs: dict[str, ExtractorConfig] = {}
        for extraction in document.extractions():
            extractor_config = ExtractorConfig.from_id_and_parent_path(
                str(extraction.extractor_config_id), project.path
            )
            if extractor_config:
                extractor_configs[str(extraction.extractor_config_id)] = (
                    extractor_config
                )

        return [
            ExtractionSummary(
                **extraction.model_dump(exclude={"output"}),
                output_content=extraction.output_content() or "",
                extractor=ExtractorSummary(
                    **extractor_configs[str(extraction.extractor_config_id)].model_dump(
                        exclude={"properties"}
                    ),
                ),
            )
            for extraction in document.extractions()
        ]

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

        return ExtractionSummary(
            **extraction.model_dump(exclude={"output"}),
            output_content=extraction.output_content() or "",
            extractor=ExtractorSummary(
                **extractor_config.model_dump(exclude={"properties"}),
            ),
        )

    @app.get("/api/projects/{project_id}/documents/{document_id}/discover_serve_file")
    async def discover_serve_document_file(
        project_id: str,
        document_id: str,
    ) -> DiscoverServeFileResponse:
        # frontend calls this to get the full URL that serves the file.
        # this avoids needing to hardcode the URL in the frontend.
        return DiscoverServeFileResponse(
            # TODO: load base URL from config
            url=f"http://localhost:8757/api/projects/{project_id}/documents/{document_id}/serve_file",
        )

    @app.get("/api/projects/{project_id}/documents/{document_id}/serve_file")
    async def serve_document_file(
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

        document_count_total = len(project.documents())
        document_count_successful = 0
        for document in project.documents():
            extractions = document.extractions()
            if any(
                extraction.extractor_config_id == extractor_config_id
                for extraction in extractions
            ):
                document_count_successful += 1

        # NOTE: could make sense to persist failed extractions (with some property like "status" / "failed_reason") to
        # be able to surface failures here (as opposed to pending extractions), and also show the actual error
        # as some may be due to some provider-specific rejection (e.g. "file too large", "wrong codec", etc.) we cannot resolve
        return ExtractionProgress(
            document_count_total=document_count_total,
            document_count_successful=document_count_successful,
            current_extractor_config=extractor_config,
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
                    ec for ec in project.extractor_configs() if not ec.is_archived
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
