---
status: draft
---

# Component: API Layer

## File Location

`app/desktop/studio_server/doc_skill_api.py`

## Registration

Add to `app/desktop/studio_server/webhost.py` (or wherever the FastAPI app is assembled) following the same pattern as `skill_api.py`:

```python
from studio_server.doc_skill_api import connect_doc_skill_api
connect_doc_skill_api(app)
```

## Request/Response Models

```python
class CreateDocSkillRequest(BaseModel):
    name: str
    skill_name: str
    skill_content_header: str
    description: str | None = None
    extractor_config_id: str
    chunker_config_id: str
    document_tags: list[str] | None = None
    strip_file_extensions: bool = True

class UpdateDocSkillRequest(BaseModel):
    is_archived: bool

class DocSkillResponse(BaseModel):
    """Response model for DocumentSkill."""
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
    created_at: datetime | None = None
    created_by: str | None = None

class DocSkillProgressRequest(BaseModel):
    """Request for batch progress. Same pattern as RAG's GetRagConfigProgressRequest."""
    doc_skill_ids: list[str] | None = None

class DocSkillSourceResponse(BaseModel):
    """Response for checking if a skill was created by a DocSkill."""
    doc_skill_id: str | None
    doc_skill_name: str | None
```

## Endpoints

### `connect_doc_skill_api(app)`

```python
def connect_doc_skill_api(app: FastAPI):

    @app.post("/api/projects/{project_id}/doc_skills", tags=["Doc Skills"])
    async def create_doc_skill(project_id: str, request: CreateDocSkillRequest) -> DocSkillResponse:
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

    @app.get("/api/projects/{project_id}/doc_skills", tags=["Doc Skills"])
    async def list_doc_skills(project_id: str) -> list[DocSkillResponse]:
        project = project_from_id(project_id)
        doc_skills = project.document_skills(readonly=True)
        return [_to_response(ds) for ds in doc_skills if not ds.is_archived]

    @app.get("/api/projects/{project_id}/doc_skills/{doc_skill_id}", tags=["Doc Skills"])
    async def get_doc_skill(project_id: str, doc_skill_id: str) -> DocSkillResponse:
        project = project_from_id(project_id)
        doc_skill = _get_doc_skill(project, doc_skill_id)
        return _to_response(doc_skill)

    @app.patch("/api/projects/{project_id}/doc_skills/{doc_skill_id}", tags=["Doc Skills"])
    async def update_doc_skill(
        project_id: str, doc_skill_id: str, request: UpdateDocSkillRequest
    ) -> DocSkillResponse:
        project = project_from_id(project_id)
        doc_skill = _get_doc_skill(project, doc_skill_id)

        doc_skill.is_archived = request.is_archived
        doc_skill.save_to_file()

        # Archive cascade: sync Skill archive state
        if doc_skill.skill_id:
            skill = Skill.from_id_and_parent_path(doc_skill.skill_id, project.path)
            if skill:
                skill.is_archived = request.is_archived
                skill.save_to_file()

        return _to_response(doc_skill)

    @app.get("/api/projects/{project_id}/doc_skills/{doc_skill_id}/run", tags=["Doc Skills"])
    async def run_doc_skill(project_id: str, doc_skill_id: str) -> StreamingResponse:
        project = project_from_id(project_id)
        doc_skill = _get_doc_skill(project, doc_skill_id)

        if doc_skill.is_archived:
            raise HTTPException(status_code=422, detail="Cannot run an archived doc skill.")
        if doc_skill.skill_id is not None:
            raise HTTPException(status_code=422, detail="This doc skill has already been built.")

        async def runner_factory():
            return await _build_workflow_runner(project, doc_skill)

        return await run_doc_skill_workflow_with_status(runner_factory)

    @app.post(
        "/api/projects/{project_id}/doc_skills/progress",
        tags=["Doc Skills"],
    )
    async def get_doc_skill_progress(
        project_id: str,
        request: DocSkillProgressRequest,
    ) -> dict[str, DocSkillProgress]:
        """Batch progress endpoint. Same pattern as RAG's /rag_configs/progress."""
        project = project_from_id(project_id)
        doc_skills: list[DocumentSkill] = []

        if request.doc_skill_ids:
            for doc_skill_id in request.doc_skill_ids:
                doc_skill = DocumentSkill.from_id_and_parent_path(doc_skill_id, project.path)
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
        }

    @app.get(
        "/api/projects/{project_id}/skills/{skill_id}/doc_skill_source",
        tags=["Doc Skills"],
    )
    async def get_doc_skill_source(
        project_id: str, skill_id: str
    ) -> DocSkillSourceResponse:
        """Check if a skill was created by a DocSkill. Used for cross-linking on skill detail page."""
        project = project_from_id(project_id)
        for ds in project.document_skills(readonly=True):
            if ds.skill_id == skill_id:
                return DocSkillSourceResponse(doc_skill_id=ds.id, doc_skill_name=ds.name)
        return DocSkillSourceResponse(doc_skill_id=None, doc_skill_name=None)
```

## SSE Streaming

```python
async def run_doc_skill_workflow_with_status(
    runner_factory: Callable[[], Awaitable[DocSkillWorkflowRunner]],
) -> StreamingResponse:
    """Wrap a DocSkillWorkflowRunner in an SSE StreamingResponse.
    Same pattern as run_rag_workflow_runner_with_status."""

    async def event_generator():
        try:
            runner = await runner_factory()
        except Exception as e:
            # Initialization error — report and close
            error_data = {"logs": [{"message": str(e), "level": "error"}]}
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        try:
            async for progress in runner.run():
                data = _serialize_progress(progress)
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.TimeoutError:
            error_data = {
                "logs": [{"message": "Pipeline timed out waiting for lock.", "level": "error"}]
            }
            yield f"data: {json.dumps(error_data)}\n\n"
        except Exception as e:
            error_data = {"logs": [{"message": str(e), "level": "error"}]}
            yield f"data: {json.dumps(error_data)}\n\n"

        yield "data: complete\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
```

## Progress Computation

```python
def compute_doc_skill_progress(project: Project, doc_skill: DocumentSkill) -> DocSkillProgress:
    """Compute current progress from disk state."""
    if doc_skill.skill_id is not None:
        # Already complete
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
            # Check for chunks under matching extractions
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
```

## Helper Functions

```python
def _get_doc_skill(project: Project, doc_skill_id: str) -> DocumentSkill:
    doc_skill = DocumentSkill.from_id_and_parent_path(doc_skill_id, project.path)
    if doc_skill is None:
        raise HTTPException(status_code=404, detail="Doc skill not found.")
    return doc_skill

def _to_response(doc_skill: DocumentSkill) -> DocSkillResponse:
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

async def _build_workflow_runner(
    project: Project, doc_skill: DocumentSkill
) -> DocSkillWorkflowRunner:
    extractor_config = ExtractorConfig.from_id_and_parent_path(
        doc_skill.extractor_config_id, project.path
    )
    if extractor_config is None:
        raise HTTPException(status_code=422, detail="Extractor config not found.")

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

def _get_filtered_documents(project: Project, tags: list[str] | None) -> list[Document]:
    all_docs = project.documents(readonly=True)
    if tags is None:
        return all_docs
    return [d for d in all_docs if d.tags and any(t in tags for t in d.tags)]
```

## Clone Flow

Clone is a UI-only feature — no dedicated API endpoint. The frontend "Clone" button on the detail page navigates to the creation form with a `clone={doc_skill_id}` URL parameter. The form fetches the source DocSkill via `GET /doc_skills/{id}` and pre-fills all fields. The user can edit any field before submitting. Submission uses the standard `POST /doc_skills` + `GET /run` flow.

## Tests

File: `app/desktop/studio_server/test_doc_skill_api.py`

Test cases:
- Create doc skill: valid request, missing required fields, invalid skill name
- List doc skills: excludes archived, returns correct fields
- Get doc skill: found, not found (404)
- Update (archive): sets is_archived, cascades to Skill
- Update (unarchive): restores both
- Run: success with SSE events, already built (422), archived (422)
- Run: validates extractor/chunker config exists
- Progress (batch): complete state, in-progress state, specific IDs, all in project
- Doc skill source: skill with source, skill without source
- SSE serialization format matches expected shape
