import base64
import binascii
import logging
from datetime import datetime
from typing import Annotated, List, Literal

from fastapi import FastAPI, HTTPException, Path, Query
from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.skill_bundle import (
    SkillBundleValidationError,
    clone_skill,
    create_skill_with_files,
)
from kiln_ai.utils.filesystem import open_folder
from kiln_ai.utils.validation import SkillNameString
from kiln_server.document_api import OpenFileResponse
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Cap on how much file content the resource_content endpoint will read into
# memory and base64-encode into a JSON response. Installed bundles cap files at
# 512KB, but hand-added files (via the enclosing folder) can be any size.
MAX_RESOURCE_CONTENT_BYTES = 10 * 1024 * 1024


class SkillFileParam(BaseModel):
    """A resource file to include in a skill bundle."""

    path: str = Field(
        description="Path within the skill bundle, starting with 'references/' or 'assets/'. Forward slashes only."
    )
    content: str = Field(
        description="File content: plain text for utf-8 encoding, base64 string for base64 encoding."
    )
    encoding: Literal["utf-8", "base64"] = Field(
        default="utf-8",
        description="How the content field is encoded. Use base64 for binary files.",
    )


class SkillCreationRequest(BaseModel):
    """Request to create a new skill."""

    name: SkillNameString = Field(description="The name of the skill.")
    description: str = Field(
        min_length=1,
        max_length=1024,
        description="What the skill does and when to use it.",
    )
    body: str = Field(min_length=1, description="The markdown body of the skill.")
    files: List[SkillFileParam] = Field(
        default_factory=list,
        description="Optional resource files (references/… and assets/…) installed atomically with the skill.",
    )


class SkillCloneRequest(BaseModel):
    """Request to clone a skill, copying all its reference and asset files."""

    name: SkillNameString = Field(description="The name of the new skill.")
    description: str = Field(
        min_length=1,
        max_length=1024,
        description="What the skill does and when to use it.",
    )
    body: str | None = Field(
        default=None,
        description="The markdown body of the new skill. Defaults to the source skill's body.",
    )


class SkillResourceInfo(BaseModel):
    """A resource file within a skill bundle."""

    path: str = Field(
        description="Bundle-relative path, starting with 'references/' or 'assets/'."
    )
    size_bytes: int = Field(description="File size in bytes.")


class SkillResourceContentResponse(BaseModel):
    """The content of a single skill resource file."""

    path: str = Field(description="Bundle-relative path of the file.")
    encoding: Literal["utf-8", "base64"] = Field(
        description="How content is encoded: utf-8 for text files, base64 for binary."
    )
    content: str = Field(description="The file content in the stated encoding.")


class SkillUpdateRequest(BaseModel):
    """Request to update a skill."""

    is_archived: bool | None = Field(
        default=None, description="Whether the skill is archived."
    )


class SkillResponse(BaseModel):
    """A skill with its metadata."""

    id: str | None = Field(
        default=None, description="The unique identifier of the skill."
    )
    name: str = Field(description="The human-readable name of the skill.")
    description: str = Field(description="What the skill does.")
    is_archived: bool = Field(
        default=False, description="Whether the skill is archived."
    )
    created_by: str | None = Field(
        default=None, description="The user who created the skill."
    )
    created_at: datetime | None = Field(
        default=None, description="When the skill was created."
    )


class SkillContentResponse(BaseModel):
    """The full content of a skill including its markdown body."""

    skill_md: str = Field(
        description="The full SKILL.md content including frontmatter."
    )
    body: str = Field(description="The markdown body of the skill.")


def skill_to_response(skill: Skill) -> SkillResponse:
    return SkillResponse.model_validate(skill.model_dump())


def _get_skill(project_id: str, skill_id: str) -> Skill:
    project = project_from_id(project_id)
    skill = Skill.from_id_and_parent_path(skill_id, project.path)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


def _decode_files(files: List[SkillFileParam]) -> dict[str, bytes]:
    """Decode request files to bytes, keyed by bundle-relative path."""
    errors: list[str] = []
    decoded: dict[str, bytes] = {}
    for file in files:
        if file.path in decoded:
            errors.append(f"duplicate file path: {file.path!r}")
            continue
        if file.encoding == "utf-8":
            try:
                decoded[file.path] = file.content.encode("utf-8")
            except UnicodeEncodeError:
                errors.append(
                    f"file content is not encodable as UTF-8 (contains lone "
                    f"surrogates): {file.path!r}"
                )
        else:
            try:
                decoded[file.path] = base64.b64decode(file.content, validate=True)
            except (binascii.Error, ValueError):
                errors.append(f"file content is not valid base64: {file.path!r}")
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    return decoded


def connect_skill_api(app: FastAPI):
    @app.get(
        "/api/projects/{project_id}/skills", tags=["Skills"], openapi_extra=ALLOW_AGENT
    )
    async def get_skills(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> List[SkillResponse]:
        project = project_from_id(project_id)
        return [skill_to_response(s) for s in project.skills(readonly=True)]

    @app.get(
        "/api/projects/{project_id}/skills/{skill_id}",
        tags=["Skills"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_skill(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
    ) -> SkillResponse:
        skill = _get_skill(project_id, skill_id)
        return skill_to_response(skill)

    @app.get(
        "/api/projects/{project_id}/skills/{skill_id}/content",
        tags=["Skills"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_skill_content(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
    ) -> SkillContentResponse:
        project = project_from_id(project_id)
        skill = Skill.from_id_and_parent_path(skill_id, project.path)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        try:
            skill_md = skill.skill_md_raw()
        except FileNotFoundError:
            skill_md = ""
        try:
            body = skill.body()
        except (FileNotFoundError, ValueError) as e:
            logger.warning("Failed to parse body for skill %s: %s", skill_id, e)
            body = ""
        return SkillContentResponse(skill_md=skill_md, body=body)

    @app.post(
        "/api/projects/{project_id}/skills", tags=["Skills"], openapi_extra=ALLOW_AGENT
    )
    async def create_skill(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_data: SkillCreationRequest,
    ) -> SkillResponse:
        project = project_from_id(project_id)
        try:
            skill = create_skill_with_files(
                project,
                name=skill_data.name,
                description=skill_data.description,
                body=skill_data.body,
                files=_decode_files(skill_data.files),
            )
        except SkillBundleValidationError as e:
            raise HTTPException(status_code=422, detail="; ".join(e.errors)) from e
        return skill_to_response(skill)

    @app.post(
        "/api/projects/{project_id}/skills/{skill_id}/clone",
        tags=["Skills"],
        openapi_extra=ALLOW_AGENT,
    )
    async def clone_skill_endpoint(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill to clone.")
        ],
        clone_data: SkillCloneRequest,
    ) -> SkillResponse:
        project = project_from_id(project_id)
        source = Skill.from_id_and_parent_path(skill_id, project.path)
        if source is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        body = clone_data.body
        if body is None:
            try:
                body = source.body()
            except (FileNotFoundError, ValueError) as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Source skill has no readable body; provide one: {e}",
                ) from e
        try:
            skill = clone_skill(
                project,
                source,
                name=clone_data.name,
                description=clone_data.description,
                body=body,
            )
        except SkillBundleValidationError as e:
            raise HTTPException(status_code=422, detail="; ".join(e.errors)) from e
        return skill_to_response(skill)

    @app.get(
        "/api/projects/{project_id}/skills/{skill_id}/resources",
        tags=["Skills"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_skill_resources(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
    ) -> List[SkillResourceInfo]:
        skill = _get_skill(project_id, skill_id)
        if skill.path is None:
            raise HTTPException(status_code=500, detail="Skill path not found")
        skill_dir = skill.path.parent
        resources: List[SkillResourceInfo] = []
        for resource_path in skill.list_resource_files():
            try:
                size_bytes = (skill_dir / resource_path).stat().st_size
            except OSError:
                # File vanished between listing and stat (e.g. the user is
                # editing the folder directly) — skip it, don't fail the list.
                continue
            resources.append(
                SkillResourceInfo(path=resource_path, size_bytes=size_bytes)
            )
        return resources

    @app.get(
        "/api/projects/{project_id}/skills/{skill_id}/resource_content",
        tags=["Skills"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_skill_resource_content(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
        path: Annotated[
            str,
            Query(
                description="Bundle-relative resource path, starting with 'references/' or 'assets/'."
            ),
        ],
    ) -> SkillResourceContentResponse:
        skill = _get_skill(project_id, skill_id)
        try:
            size_bytes = skill.resource_size_bytes(path)
            if size_bytes > MAX_RESOURCE_CONTENT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Resource is {size_bytes} bytes, over the "
                        f"{MAX_RESOURCE_CONTENT_BYTES} byte limit for this endpoint: {path}"
                    ),
                )
            data = skill.read_resource_bytes(path)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Resource not found: {path}"
            ) from None
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        try:
            return SkillResourceContentResponse(
                path=path, encoding="utf-8", content=data.decode("utf-8")
            )
        except UnicodeDecodeError:
            return SkillResourceContentResponse(
                path=path,
                encoding="base64",
                content=base64.b64encode(data).decode("ascii"),
            )

    @app.patch(
        "/api/projects/{project_id}/skills/{skill_id}",
        tags=["Skills"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to edit skill? Ensure you backup your project before allowing agentic edits."
        ),
    )
    async def update_skill(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
        updates: SkillUpdateRequest,
    ) -> SkillResponse:
        skill = _get_skill(project_id, skill_id)

        update_fields = updates.model_dump(exclude_none=True)
        merged = skill.model_dump()
        merged.update(update_fields)
        updated = Skill.model_validate(merged)
        updated.path = skill.path
        updated.save_to_file()

        return skill_to_response(updated)

    @app.post(
        "/api/projects/{project_id}/skills/{skill_id}/open_enclosing_folder",
        tags=["Skills"],
        openapi_extra=DENY_AGENT,
    )
    async def open_skill_enclosing_folder(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
    ) -> OpenFileResponse:
        skill = _get_skill(project_id, skill_id)
        if not skill.path:
            raise HTTPException(
                status_code=500,
                detail="Skill path not found",
            )
        open_folder(skill.path)
        return OpenFileResponse(path=str(skill.path.parent))
