from typing import List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.skill import Skill
from kiln_ai.utils.validation import ToolNameString
from kiln_server.project_api import project_from_id
from pydantic import BaseModel, Field


class SkillCreationRequest(BaseModel):
    name: ToolNameString
    description: str = Field(min_length=1, max_length=1024)
    body: str = Field(min_length=1)


class SkillUpdateRequest(BaseModel):
    name: ToolNameString | None = None
    description: str | None = Field(default=None, min_length=1, max_length=1024)
    body: str | None = Field(default=None, min_length=1)
    is_archived: bool | None = None


def connect_skill_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/skills")
    async def get_skills(project_id: str) -> List[Skill]:
        project = project_from_id(project_id)
        return project.skills(readonly=True)

    @app.get("/api/projects/{project_id}/skills/{skill_id}")
    async def get_skill(project_id: str, skill_id: str) -> Skill:
        project = project_from_id(project_id)
        skill = Skill.from_id_and_parent_path(skill_id, project.path)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        return skill

    @app.post("/api/projects/{project_id}/skills")
    async def create_skill(project_id: str, skill_data: SkillCreationRequest) -> Skill:
        project = project_from_id(project_id)
        skill = Skill(
            name=skill_data.name,
            description=skill_data.description,
            body=skill_data.body,
            parent=project,
        )
        skill.save_to_file()
        return skill

    @app.patch("/api/projects/{project_id}/skills/{skill_id}")
    async def update_skill(
        project_id: str, skill_id: str, updates: SkillUpdateRequest
    ) -> Skill:
        project = project_from_id(project_id)
        skill = Skill.from_id_and_parent_path(skill_id, project.path)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")

        update_fields = updates.model_dump(exclude_none=True)
        merged = skill.model_dump()
        merged.update(update_fields)
        updated = Skill.model_validate(merged)
        updated.path = skill.path
        updated.save_to_file()

        return updated
