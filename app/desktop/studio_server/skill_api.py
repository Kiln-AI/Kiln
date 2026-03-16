from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.skill import Skill
from kiln_ai.utils.validation import SkillNameString
from kiln_server.project_api import project_from_id
from pydantic import BaseModel, Field


class SkillCreationRequest(BaseModel):
    name: SkillNameString
    description: str = Field(min_length=1, max_length=1024)
    body: str = Field(min_length=1)


class SkillUpdateRequest(BaseModel):
    is_archived: bool | None = None


class SkillResponse(BaseModel):
    id: str | None = None
    name: str
    description: str
    is_archived: bool = False
    created_by: str | None = None
    created_at: datetime | None = None


class SkillContentResponse(BaseModel):
    skill_md: str
    body: str


def skill_to_response(skill: Skill) -> SkillResponse:
    return SkillResponse.model_validate(skill.model_dump())


def _get_skill(project_id: str, skill_id: str) -> Skill:
    project = project_from_id(project_id)
    skill = Skill.from_id_and_parent_path(skill_id, project.path)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


def connect_skill_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/skills")
    async def get_skills(project_id: str) -> List[SkillResponse]:
        project = project_from_id(project_id)
        return [skill_to_response(s) for s in project.skills(readonly=True)]

    @app.get("/api/projects/{project_id}/skills/{skill_id}")
    async def get_skill(project_id: str, skill_id: str) -> SkillResponse:
        skill = _get_skill(project_id, skill_id)
        return skill_to_response(skill)

    @app.get("/api/projects/{project_id}/skills/{skill_id}/content")
    async def get_skill_content(project_id: str, skill_id: str) -> SkillContentResponse:
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
        except FileNotFoundError:
            body = ""
        return SkillContentResponse(skill_md=skill_md, body=body)

    @app.post("/api/projects/{project_id}/skills")
    async def create_skill(
        project_id: str, skill_data: SkillCreationRequest
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

    @app.patch("/api/projects/{project_id}/skills/{skill_id}")
    async def update_skill(
        project_id: str, skill_id: str, updates: SkillUpdateRequest
    ) -> SkillResponse:
        skill = _get_skill(project_id, skill_id)

        update_fields = updates.model_dump(exclude_none=True)
        merged = skill.model_dump()
        merged.update(update_fields)
        updated = Skill.model_validate(merged)
        updated.path = skill.path
        updated.save_to_file()

        return skill_to_response(updated)
