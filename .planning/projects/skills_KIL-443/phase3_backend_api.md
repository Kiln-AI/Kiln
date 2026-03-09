# Phase 3: Backend API

## Goal

Add FastAPI CRUD endpoints for skills and integrate skills into the available_tools API response.

## Files to Create/Modify

### New: `app/desktop/studio_server/skill_api.py`

CRUD API for skills, following the existing patterns from `task_api.py` and the RAG config APIs.

```python
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.skill import Skill
from kiln_server.project_api import project_from_id


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
    async def create_skill(project_id: str, skill_data: Dict[str, Any]) -> Skill:
        project = project_from_id(project_id)

        skill = Skill.validate_and_save_with_subrelations(
            skill_data, parent=project
        )

        return skill

    @app.patch("/api/projects/{project_id}/skills/{skill_id}")
    async def update_skill(
        project_id: str, skill_id: str, updates: Dict[str, Any]
    ) -> Skill:
        project = project_from_id(project_id)
        skill = Skill.from_id_and_parent_path(skill_id, project.path)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")

        updated = skill.model_copy(update=updates)
        updated.save_to_file()

        return updated

    @app.delete("/api/projects/{project_id}/skills/{skill_id}")
    async def delete_skill(project_id: str, skill_id: str) -> None:
        project = project_from_id(project_id)
        skill = Skill.from_id_and_parent_path(skill_id, project.path)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        skill.delete()
```

Note: The API uses `name` and `description` directly — matching the `Skill` model fields. No mapping needed.

### Modify: `app/desktop/studio_server/tool_api.py`

Add skills to the available_tools response:

```python
# Add to ToolSetType enum:
class ToolSetType(Enum):
    SEARCH = "search"
    MCP = "mcp"
    KILN_TASK = "kiln_task"
    DEMO = "demo"
    SKILL = "skill"  # NEW

# In get_available_tools(), add after existing tool sets:
skills = project.skills(readonly=True)
if skills:
    skill_tools = [
        ToolApiDescription(
            id=build_skill_tool_id(skill.id),
            name=skill.name,
            description=skill.description,
        )
        for skill in skills
    ]
    if skill_tools:
        tool_sets.append(
            ToolSetApiDescription(
                type=ToolSetType.SKILL,
                set_name="Skills",
                tools=skill_tools,
            )
        )
```

### Modify: `app/desktop/studio_server/server.py`

Register the new skill API:

```python
from app.desktop.studio_server.skill_api import connect_skill_api

# In the server setup:
connect_skill_api(app)
```

### New: `app/desktop/studio_server/test_skill_api.py`

Tests:

1. **CRUD tests**:
   - POST create skill with valid data → 200, returns skill with ID
   - POST create skill with invalid name → 422 validation error
   - GET list skills → returns all skills for project
   - GET single skill → returns skill by ID
   - GET non-existent skill → 404
   - PATCH update skill → updates fields
   - DELETE skill → removes from disk

2. **Available tools integration**:
   - GET available_tools includes skills in response
   - Skills tool set has type "skill"
   - Skills with correct IDs and descriptions

## Key Design Notes

- The API uses `name` and `description` directly — same fields as the `Skill` model, no mapping needed
- Skills appear in `available_tools` alongside other tool types (search, mcp, kiln_task, demo)
- The `build_skill_tool_id` function from tool_id.py is used for consistent ID generation
