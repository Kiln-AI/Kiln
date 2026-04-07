import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import StreamingResponse
from kiln_ai.adapters.rag.progress import LogMessage
from kiln_ai.datamodel.chunk import ChunkerConfig
from kiln_ai.datamodel.document_skill import DocumentSkill
from kiln_ai.datamodel.extraction import Document, ExtractorConfig
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
from pydantic import BaseModel

from kiln_ai.adapters.rag.deduplication import filter_documents_by_tags
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT, DENY_AGENT

from .doc_skill_pipeline import (
    DocSkillProgress,
    DocSkillWorkflowRunner,
    DocSkillWorkflowRunnerConfig,
)

logger = logging.getLogger(__name__)


class CreateDocSkillRequest(BaseModel):
    """Request to create a new document skill configuration."""

    name: str
    skill_name: str
    skill_content_header: str
    description: str | None = None
    extractor_config_id: str
    chunker_config_id: str
    document_tags: list[str] | None = None
    strip_file_extensions: bool = True


class UpdateDocSkillRequest(BaseModel):
    """Request to archive or unarchive a document skill."""

    is_archived: bool


class DocSkillResponse(BaseModel):
    """A document skill configuration with its metadata."""

    id: str
    name: str
    skill_name: str
    skill_content_header: str
    description: str | None
    extractor_config_id: str
    chunker_config_id: str
    document_tags: list[str] | None
    skill_id: str | None
    strip_file_extensions: bool
    is_archived: bool
    created_at: datetime | None
    created_by: str | None


class DocSkillProgressRequest(BaseModel):
    """Request for batch doc skill progress. If doc_skill_ids is None, returns all."""

    doc_skill_ids: list[str] | None = None


class DocSkillSourceResponse(BaseModel):
    """Links a generated skill back to its source document skill."""

    doc_skill_id: str | None
    doc_skill_name: str | None


def _get_doc_skill(project: Project, doc_skill_id: str) -> DocumentSkill:
    doc_skill = DocumentSkill.from_id_and_parent_path(doc_skill_id, project.path)
    if doc_skill is None:
        raise HTTPException(status_code=404, detail="Doc skill not found.")
    return doc_skill


def _to_response(doc_skill: DocumentSkill) -> DocSkillResponse:
    if (
        doc_skill.id is None
        or doc_skill.extractor_config_id is None
        or doc_skill.chunker_config_id is None
    ):
        raise HTTPException(
            status_code=500,
            detail="Doc skill is missing required fields.",
        )
    return DocSkillResponse(
        id=doc_skill.id,
        name=doc_skill.name,
        skill_name=doc_skill.skill_name,
        skill_content_header=doc_skill.skill_content_header,
        description=doc_skill.description,
        extractor_config_id=doc_skill.extractor_config_id,
        chunker_config_id=doc_skill.chunker_config_id,
        document_tags=doc_skill.document_tags,
        skill_id=doc_skill.skill_id,
        strip_file_extensions=doc_skill.strip_file_extensions,
        is_archived=doc_skill.is_archived,
        created_at=doc_skill.created_at,
        created_by=doc_skill.created_by,
    )


def _get_filtered_documents(project: Project, tags: list[str] | None) -> list[Document]:
    all_docs = project.documents(readonly=True)
    if tags is None:
        return all_docs
    return filter_documents_by_tags(all_docs, tags)


def compute_doc_skill_progress(
    project: Project, doc_skill: DocumentSkill
) -> DocSkillProgress:
    if doc_skill.skill_id is not None:
        docs = _get_filtered_documents(project, doc_skill.document_tags)
        return DocSkillProgress(
            total_document_count=len(docs),
            total_document_extracted_count=len(docs),
            total_document_chunked_count=len(docs),
            skill_created=True,
        )

    docs = _get_filtered_documents(project, doc_skill.document_tags)
    extracted = 0
    chunked = 0

    for doc in docs:
        has_extraction = any(
            ext.extractor_config_id == doc_skill.extractor_config_id
            for ext in doc.extractions()
        )
        if has_extraction:
            extracted += 1
            for ext in doc.extractions():
                if ext.extractor_config_id == doc_skill.extractor_config_id:
                    has_chunks = any(
                        cd.chunker_config_id == doc_skill.chunker_config_id
                        for cd in ext.chunked_documents()
                    )
                    if has_chunks:
                        chunked += 1
                    break

    return DocSkillProgress(
        total_document_count=len(docs),
        total_document_extracted_count=extracted,
        total_document_chunked_count=chunked,
        skill_created=False,
    )


async def _build_workflow_runner(
    project: Project, doc_skill: DocumentSkill
) -> DocSkillWorkflowRunner:
    if not doc_skill.extractor_config_id:
        raise HTTPException(status_code=422, detail="Extractor config not found.")
    extractor_config = ExtractorConfig.from_id_and_parent_path(
        doc_skill.extractor_config_id, project.path
    )
    if extractor_config is None:
        raise HTTPException(status_code=422, detail="Extractor config not found.")

    if not doc_skill.chunker_config_id:
        raise HTTPException(status_code=422, detail="Chunker config not found.")
    chunker_config = ChunkerConfig.from_id_and_parent_path(
        doc_skill.chunker_config_id, project.path
    )
    if chunker_config is None:
        raise HTTPException(status_code=422, detail="Chunker config not found.")

    config = DocSkillWorkflowRunnerConfig(
        doc_skill=doc_skill,
        project=project,
        extractor_config=extractor_config,
        chunker_config=chunker_config,
    )

    initial_progress = compute_doc_skill_progress(project, doc_skill)
    return DocSkillWorkflowRunner(config, initial_progress)


def _serialize_progress(progress: DocSkillProgress) -> dict:
    return {
        "total_document_count": progress.total_document_count,
        "total_document_extracted_count": progress.total_document_extracted_count,
        "total_document_extracted_error_count": progress.total_document_extracted_error_count,
        "total_document_chunked_count": progress.total_document_chunked_count,
        "total_document_chunked_error_count": progress.total_document_chunked_error_count,
        "skill_created": progress.skill_created,
        "logs": [
            {"message": log.message, "level": log.level}
            for log in (progress.logs or [])
        ],
    }


async def run_doc_skill_workflow_with_status(
    runner_factory: Callable[[], Awaitable[DocSkillWorkflowRunner]],
) -> StreamingResponse:
    async def event_generator():
        latest_progress = DocSkillProgress()

        try:
            runner = await runner_factory()
            async for progress in runner.run():
                latest_progress = progress.model_copy()
                data = _serialize_progress(progress)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except asyncio.TimeoutError:
            logger.info("Doc skill workflow runner timed out waiting for lock")
            latest_progress.logs = [
                LogMessage(
                    level="error",
                    message="Timed out after waiting for the lock to be acquired. This may be due to a concurrent pipeline running. You may retry in a few minutes.",
                )
            ]
            data = _serialize_progress(latest_progress)
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(
                f"Unexpected server error running doc skill workflow: {e}",
                exc_info=True,
            )
            latest_progress.logs = [
                LogMessage(
                    level="error",
                    message=f"Unexpected server error: {e}",
                )
            ]
            data = _serialize_progress(latest_progress)
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield "data: complete\n\n"

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
    )


ProjectId = Annotated[str, Path(description="The unique identifier of the project.")]
DocSkillId = Annotated[str, Path(description="The unique identifier of the doc skill.")]
SkillId = Annotated[str, Path(description="The unique identifier of the skill.")]


def connect_doc_skill_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/doc_skills",
        tags=["Doc Skills"],
        summary="Create Doc Skill",
        openapi_extra=DENY_AGENT,
    )
    async def create_doc_skill(
        project_id: ProjectId, request: CreateDocSkillRequest
    ) -> DocSkillResponse:
        project = project_from_id(project_id)

        doc_skill = DocumentSkill(
            name=request.name,
            skill_name=request.skill_name,
            skill_content_header=request.skill_content_header,
            description=request.description,
            extractor_config_id=request.extractor_config_id,
            chunker_config_id=request.chunker_config_id,
            document_tags=request.document_tags,
            strip_file_extensions=request.strip_file_extensions,
        )
        doc_skill.parent = project
        doc_skill.save_to_file()
        return _to_response(doc_skill)

    @app.get(
        "/api/projects/{project_id}/doc_skills",
        tags=["Doc Skills"],
        summary="List Doc Skills",
        openapi_extra=ALLOW_AGENT,
    )
    async def list_doc_skills(project_id: ProjectId) -> list[DocSkillResponse]:
        project = project_from_id(project_id)
        doc_skills = project.document_skills(readonly=True)
        return [_to_response(ds) for ds in doc_skills]

    @app.get(
        "/api/projects/{project_id}/doc_skills/{doc_skill_id}",
        tags=["Doc Skills"],
        summary="Get Doc Skill",
        openapi_extra=ALLOW_AGENT,
    )
    async def get_doc_skill(
        project_id: ProjectId, doc_skill_id: DocSkillId
    ) -> DocSkillResponse:
        project = project_from_id(project_id)
        doc_skill = _get_doc_skill(project, doc_skill_id)
        return _to_response(doc_skill)

    @app.patch(
        "/api/projects/{project_id}/doc_skills/{doc_skill_id}",
        tags=["Doc Skills"],
        summary="Update Doc Skill",
        openapi_extra=DENY_AGENT,
    )
    async def update_doc_skill(
        project_id: ProjectId, doc_skill_id: DocSkillId, request: UpdateDocSkillRequest
    ) -> DocSkillResponse:
        project = project_from_id(project_id)
        doc_skill = _get_doc_skill(project, doc_skill_id)

        doc_skill.is_archived = request.is_archived
        doc_skill.save_to_file()

        if doc_skill.skill_id:
            skill = Skill.from_id_and_parent_path(doc_skill.skill_id, project.path)
            if skill:
                skill.is_archived = request.is_archived
                skill.save_to_file()

        return _to_response(doc_skill)

    @app.get(
        "/api/projects/{project_id}/doc_skills/{doc_skill_id}/run",
        tags=["Doc Skills"],
        summary="Run Doc Skill Pipeline",
        openapi_extra=DENY_AGENT,
    )
    async def run_doc_skill(
        project_id: ProjectId, doc_skill_id: DocSkillId
    ) -> StreamingResponse:
        """Triggers the extraction → chunking → skill creation pipeline via SSE. Uses GET for EventSource compatibility."""
        project = project_from_id(project_id)
        doc_skill = _get_doc_skill(project, doc_skill_id)

        if doc_skill.is_archived:
            raise HTTPException(
                status_code=422, detail="Cannot run an archived doc skill."
            )
        if doc_skill.skill_id is not None:
            raise HTTPException(
                status_code=422, detail="This doc skill has already been built."
            )

        async def runner_factory():
            return await _build_workflow_runner(project, doc_skill)

        return await run_doc_skill_workflow_with_status(runner_factory)

    @app.post(
        "/api/projects/{project_id}/doc_skills/progress",
        tags=["Doc Skills"],
        summary="Get Doc Skill Progress",
        openapi_extra=ALLOW_AGENT,
    )
    async def get_doc_skill_progress(
        project_id: ProjectId,
        request: DocSkillProgressRequest,
    ) -> dict[str, DocSkillProgress]:
        """Batch endpoint: returns progress for specified doc skill IDs, or all in project."""
        project = project_from_id(project_id)
        doc_skills: list[DocumentSkill] = []

        if request.doc_skill_ids is not None:
            for doc_skill_id in request.doc_skill_ids:
                doc_skill = DocumentSkill.from_id_and_parent_path(
                    doc_skill_id, project.path
                )
                if doc_skill is None:
                    continue
                doc_skills.append(doc_skill)
            if not doc_skills:
                return {}
        else:
            doc_skills = project.document_skills(readonly=True)

        return {
            ds.id: compute_doc_skill_progress(project, ds)
            for ds in doc_skills
            if ds.id is not None
        }

    @app.get(
        "/api/projects/{project_id}/skills/{skill_id}/doc_skill_source",
        tags=["Doc Skills"],
        summary="Get Doc Skill Source for Skill",
        openapi_extra=ALLOW_AGENT,
    )
    async def get_doc_skill_source(
        project_id: ProjectId, skill_id: SkillId
    ) -> DocSkillSourceResponse:
        project = project_from_id(project_id)
        for ds in project.document_skills(readonly=True):
            if ds.skill_id == skill_id:
                return DocSkillSourceResponse(
                    doc_skill_id=ds.id, doc_skill_name=ds.name
                )
        return DocSkillSourceResponse(doc_skill_id=None, doc_skill_name=None)
