import logging
import tempfile
from asyncio import Lock
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.document import Document, FileInfo
from kiln_ai.datamodel.extraction import Kind
from kiln_ai.datamodel.registry import project_from_id
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Lock to prevent overwriting via concurrent updates. We use a load/update/write pattern that is not atomic.
update_run_lock = Lock()


class CreateDocumentRequest(BaseModel):
    name: str
    description: str


def connect_document_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/documents")
    async def create_document(
        project_id: str,
        file: UploadFile = File(...),
        name: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
    ) -> Document:
        suffix = Path(file.filename).suffix if file.filename else ""
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=True, suffix=suffix
        ) as tmp_file:
            file_data = await file.read()
            tmp_file.write(file_data)

            project = project_from_id(project_id)
            if not project:
                raise HTTPException(
                    status_code=404, detail=f"Project not found: {project_id}"
                )

            document = Document(
                name=name,
                description=description,
                parent=project,
                kind=Kind.DOCUMENT,
                original_file=FileInfo(
                    filename=file.filename or "",
                    mime_type=file.content_type or "",
                    attachment=KilnAttachmentModel(path=Path(tmp_file.name)),
                    size=len(file_data),
                ),
            )
            document.save_to_file()
            return document
