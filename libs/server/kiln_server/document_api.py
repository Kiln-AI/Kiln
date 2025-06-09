import json
import logging
import os
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from kiln_ai.adapters.extractors.extractor_runner import ExtractorRunner
from kiln_ai.datamodel.basemodel import ID_TYPE, KilnAttachmentModel
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


def sanitize_name(name: str) -> str:
    return name.strip().replace(" ", "_").replace(".", "_").replace("/", "_")


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


class ExtractionWithOutput(BaseModel):
    extraction: Extraction
    output: str


class OpenFileResponse(BaseModel):
    path: str


class DiscoverServeFileResponse(BaseModel):
    url: str


class ExtractionProgress(BaseModel):
    document_count_total: int
    document_count_successful: int
    current_extractor_config: ExtractorConfig | None


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
            name=sanitize_name(name),
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
    ) -> StreamingResponse:
        project = project_from_id(project_id)
        request.name = request.name or generate_memorable_name()

        # TODO: refactor prompt_for_kind into flat properties like prompt_document, prompt_image, etc.
        # will be easier for defaults, easier for UI, etc.
        match request.extractor_type:
            case ExtractorType.GEMINI:
                output_format = request.output_format or OutputFormat.MARKDOWN
                DEFAULT_PROMPT_FOR_KIND = {
                    Kind.DOCUMENT: f"""Transcribe the document into {output_format.value}.
If the document contains images and figures, describe them in the output. For example, if the
document contains an image, describe it in the output. If the document contains a table, format it 
appropriately and add a sentence describing it as a whole.

Format the output as valid {output_format.value}.

Do NOT include any prefatory text such as 'Here is the transcription of the document:'.
""",
                    Kind.IMAGE: f"""Describe the image in {output_format.value}.
If the image contains text, transcribe it into {output_format.value}.

Do NOT include any prefatory text such as 'Here is the description of the image:'.
""",
                    Kind.VIDEO: f"""Describe what happens in the video in {output_format.value}.
Take into account the audio as well as the visual content. Your transcription must chronologically
describe the events in the video and transcribe any speech.

Do NOT include any prefatory text such as 'Here is the transcription of the video:'.
""",
                    Kind.AUDIO: f"""Transcribe the audio into {output_format.value}.
If the audio contains speech, transcribe it into {output_format.value}.

Do NOT include any prefatory text such as 'Here is the transcription of the audio:'.
""",
                }

                user_prompts: dict[str, str] = (
                    request.properties.get("prompt_for_kind") or {}  # type: ignore
                )
                # parse string keys into Kind enums if needed
                parsed_user_prompts = {
                    Kind(k) if isinstance(k, str) else k: v
                    for k, v in user_prompts.items()
                }

                # filter the empty string prompts
                parsed_user_prompts = {
                    k: v for k, v in parsed_user_prompts.items() if v and v.strip()
                }

                prompt_for_kind: dict[str, str] = {
                    **DEFAULT_PROMPT_FOR_KIND,
                    **parsed_user_prompts,
                }
                model_name = request.properties.get("model_name")
                if model_name is None:
                    model_name = "gemini-2.0-flash"
                extractor_config = ExtractorConfig(
                    parent=project,
                    name=request.name or "",
                    description=request.description or "",
                    output_format=output_format,
                    passthrough_mimetypes=request.passthrough_mimetypes or [],
                    extractor_type=request.extractor_type,
                    properties={
                        "prompt_for_kind": prompt_for_kind,
                        "model_name": model_name,
                    },
                )
            case _:
                raise ValueError(f"Invalid extractor type: {request.extractor_type}")

        extractor_config.save_to_file()

        extractor_runner = ExtractorRunner(
            extractor_configs=[extractor_config],
            documents=project.documents(),
        )
        return await run_extractor_runner_with_status(extractor_runner)

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

    @app.get(
        "/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}"
    )
    async def get_extraction(
        project_id: str,
        document_id: str,
        extraction_id: str,
    ) -> ExtractionWithOutput:
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

        return ExtractionWithOutput(
            extraction=extraction, output=extraction.output_content() or ""
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

        # system call to open folder in default OS explorer (finder, explorer, etc)
        os.system(f'open "{document.path.parent}"')

        return OpenFileResponse(path=str(document.path.parent))

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
                extractor_config.id for extractor_config in project.extractor_configs()
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
