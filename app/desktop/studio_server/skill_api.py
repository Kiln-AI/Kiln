import logging
import pathlib
from datetime import datetime
from typing import Annotated, List

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel.skill import Skill
from kiln_ai.utils.filesystem import open_folder
from kiln_ai.utils.validation import SkillNameString
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SkillCreationRequest(BaseModel):
    """Request to create a new skill."""

    name: SkillNameString = Field(description="The name of the skill.")
    description: str = Field(
        min_length=1,
        max_length=1024,
        description="What the skill does and when to use it.",
    )
    body: str = Field(min_length=1, description="The markdown body of the skill.")


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


class SkillFileCountsResponse(BaseModel):
    """Counts of files in the skill's references and assets directories."""

    reference_count: int = Field(
        description="Number of files in the references directory."
    )
    asset_count: int = Field(description="Number of files in the assets directory.")


class OpenFolderResponse(BaseModel):
    """Response after opening a folder."""

    path: str = Field(description="The path that was opened.")


def _count_files_recursive(directory: "pathlib.Path") -> int:
    if not directory.exists():
        return 0
    return sum(1 for f in directory.rglob("*") if f.is_file())


def skill_to_response(skill: Skill) -> SkillResponse:
    return SkillResponse.model_validate(skill.model_dump())


def _get_skill(project_id: str, skill_id: str) -> Skill:
    project = project_from_id(project_id)
    skill = Skill.from_id_and_parent_path(skill_id, project.path)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


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
        skill = Skill(
            name=skill_data.name,
            description=skill_data.description,
            parent=project,
        )
        skill.save_to_file()
        skill.save_skill_md(skill_data.body)
        return skill_to_response(skill)

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

    @app.get(
        "/api/projects/{project_id}/skills/{skill_id}/file_counts",
        tags=["Skills"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_skill_file_counts(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
    ) -> SkillFileCountsResponse:
        skill = _get_skill(project_id, skill_id)
        try:
            reference_count = _count_files_recursive(skill.references_dir())
        except ValueError:
            reference_count = 0
        try:
            asset_count = _count_files_recursive(skill.assets_dir())
        except ValueError:
            asset_count = 0
        return SkillFileCountsResponse(
            reference_count=reference_count,
            asset_count=asset_count,
        )

    @app.post(
        "/api/projects/{project_id}/skills/{skill_id}/open_folder",
        tags=["Skills"],
        openapi_extra=DENY_AGENT,
    )
    async def open_skill_folder(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        skill_id: Annotated[
            str, Path(description="The unique identifier of the skill.")
        ],
    ) -> OpenFolderResponse:
        skill = _get_skill(project_id, skill_id)
        if not skill.path:
            raise HTTPException(status_code=500, detail="Skill path not found")
        skill_dir = skill.path.parent
        # open_folder expects a file path (it calls os.path.dirname internally)
        open_folder(str(skill_dir / "SKILL.md"))
        return OpenFolderResponse(path=str(skill_dir))
