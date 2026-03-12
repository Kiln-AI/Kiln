from datetime import datetime
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
    is_archived: bool | None = None


class ReferenceContent(BaseModel):
    content: str = Field(min_length=1)


class SkillResponse(BaseModel):
    id: str | None = None
    name: str
    description: str
    skill_md: str
    is_archived: bool = False
    created_by: str | None = None
    created_at: datetime | None = None


def skill_to_response(skill: Skill) -> SkillResponse:
    try:
        skill_md = skill.skill_md_raw()
    except FileNotFoundError:
        skill_md = ""
    data = skill.model_dump()
    data["skill_md"] = skill_md
    return SkillResponse.model_validate(data)


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
        skill.references_dir().mkdir(parents=True, exist_ok=True)
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

    # -- Reference file endpoints --

    @app.get("/api/projects/{project_id}/skills/{skill_id}/references")
    async def list_references(project_id: str, skill_id: str) -> list[str]:
        skill = _get_skill(project_id, skill_id)
        return skill.list_references()

    @app.get("/api/projects/{project_id}/skills/{skill_id}/references/{filename}")
    async def get_reference(project_id: str, skill_id: str, filename: str) -> dict:
        skill = _get_skill(project_id, skill_id)
        try:
            content = skill.read_reference(filename)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Reference file not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"filename": filename, "content": content}

    @app.put("/api/projects/{project_id}/skills/{skill_id}/references/{filename}")
    async def save_reference(
        project_id: str, skill_id: str, filename: str, body: ReferenceContent
    ) -> dict:
        skill = _get_skill(project_id, skill_id)
        try:
            skill.save_reference(filename, body.content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"filename": filename}

    @app.delete("/api/projects/{project_id}/skills/{skill_id}/references/{filename}")
    async def delete_reference(project_id: str, skill_id: str, filename: str) -> None:
        skill = _get_skill(project_id, skill_id)
        try:
            skill.delete_reference(filename)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Reference file not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
