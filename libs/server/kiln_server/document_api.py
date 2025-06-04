import json
import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from kiln_ai.adapters.extractors.extractor_runner import ExtractorRunner
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
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
from pydantic import BaseModel

from kiln_server.project_api import project_from_id

logger = logging.getLogger(__name__)


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


class CreateDocumentRequest(BaseModel):
    name: str
    description: str


class CreateExtractorConfigRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    output_format: OutputFormat
    passthrough_mimetypes: list[OutputFormat]
    extractor_type: ExtractorType
    properties: dict[str, str | int | float | bool | dict[str, str]]


def connect_document_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/documents")
    async def create_document(
        project_id: str,
        file: UploadFile = File(...),
        name: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
    ) -> Document:
        project = project_from_id(project_id)
        suffix = Path(file.filename).suffix if file.filename else ""
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=True, suffix=suffix
        ) as tmp_file:
            file_data = await file.read()
            tmp_file.write(file_data)

            # TODO: detect kind from file
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
                name=name,
                description=description,
                kind=kind,
                original_file=FileInfo(
                    filename=file.filename or "",
                    mime_type=content_type,
                    attachment=KilnAttachmentModel(path=Path(tmp_file.name)),
                    size=len(file_data),
                ),
            )
            document.save_to_file()

            # TODO: async trigger extraction for all configs
            for extractor_config in project.extractor_configs():
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

        # TODO: maybe add cache here (readonly=True flag)
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
        name = request.name or generate_memorable_name()

        # example properties:
        # extractor_config = ExtractorConfig(
        #     parent=project,
        #     name="Gemini",
        #     extractor_type=ExtractorType.GEMINI,
        #     output_format=OutputFormat.MARKDOWN,
        #     properties={
        #         "model_name": "gemini-2.0-flash",
        #         "prompt_for_kind": {
        #             Kind.DOCUMENT: "Transcribe the document into markdown.",
        #             Kind.IMAGE: "Describe the image.",
        #             Kind.VIDEO: "Describe the video.",
        #             Kind.AUDIO: "Describe the audio.",
        #         },
        #     },
        # )

        extractor_config = ExtractorConfig(
            name=name,
            description=request.description,
            output_format=request.output_format,
            passthrough_mimetypes=request.passthrough_mimetypes,
            extractor_type=request.extractor_type,
            properties=request.properties,
            parent=project,
        )
        extractor_config.save_to_file()
        return extractor_config

    # JS SSE client (EventSource) doesn't work with POST requests, so we use GET, even though post would be better
    @app.get(
        "/api/projects/{project_id}/extractor_config/{extractor_config_id}/run_extractor_config"
    )
    async def run_extractor_config(
        project_id: str,
        extractor_config_id: str,
    ) -> StreamingResponse:
        project = project_from_id(project_id)
        extractor_config = ExtractorConfig.from_id_and_parent_path(
            extractor_config_id, project.path
        )
        if extractor_config is None:
            raise HTTPException(
                status_code=404,
                detail="Extractor config not found",
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
    ) -> list[Extraction]:
        project = project_from_id(project_id)
        document = Document.from_id_and_parent_path(document_id, project.path)
        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )

        return document.extractions()
