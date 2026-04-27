---
status: draft
---

# Phase 2: `all_tasks` Endpoint + Response Models

## Overview

Add the `GET /api/all_tasks` endpoint to `task_api.py`. This endpoint returns all projects and their tasks from the user's workspace, with task instructions truncated to 100 words. Response uses Pydantic models for OpenAPI schema generation. A `_truncate_to_words` helper handles truncation and will be reused by `agent_api.py` in Phase 5.

## Steps

1. Add `_truncate_to_words(text: str | None, max_words: int) -> tuple[str | None, bool]` helper to `task_api.py`. Returns (possibly truncated text, was_truncated). None input returns (None, False). Split on whitespace, if word count > limit keep first N words joined with single spaces and append ` …`.

2. Add Pydantic response models to `task_api.py`:
   ```python
   class AllTasksTask(BaseModel):
       id: str
       name: str
       description: str | None
       instruction: str
       instruction_truncated: bool
       created_at: datetime

   class AllTasksProject(BaseModel):
       id: str
       name: str
       description: str | None
       created_at: datetime
       tasks: list[AllTasksTask]

   class AllTasksResponse(BaseModel):
       projects: list[AllTasksProject]
   ```

3. Add the route inside `connect_task_api(app)`:
   ```python
   @app.get("/api/all_tasks", openapi_extra=ALLOW_AGENT)
   async def all_tasks() -> AllTasksResponse:
   ```
   Iterate `Config.shared().projects`, load each project, iterate `project.tasks(readonly=True)`, truncate instruction to 100 words, build response.

4. Regenerate OpenAPI schema via `generate_schema.sh`.

## Tests

- `test_all_tasks_happy_path`: 2 projects x 2 tasks each; verify nested shape and all fields present.
- `test_all_tasks_empty_workspace`: No projects configured; returns `{"projects": []}`.
- `test_all_tasks_instruction_truncation_over_limit`: Task with >100 word instruction; verify truncated to 100 words with ` …` suffix and `instruction_truncated == True`.
- `test_all_tasks_instruction_at_limit`: Task with exactly 100 words; verify not truncated, no ellipsis, `instruction_truncated == False`.
- `test_all_tasks_instruction_under_limit`: Short instruction; verify not truncated.
- `test_all_tasks_null_description`: Task/project with None description; verify null in response.
- `test_truncate_to_words_none`: None input returns (None, False).
- `test_truncate_to_words_empty`: Empty string stays empty, not truncated.
- `test_truncate_to_words_under_limit`: Returns original, False.
- `test_truncate_to_words_at_limit`: Returns original, False.
- `test_truncate_to_words_over_limit`: Truncated to N words + ` …`, True.
- `test_truncate_to_words_one_over`: N+1 words truncated to N words + ` …`, True.
- `test_all_tasks_skips_corrupt_project`: Project file that fails to load is skipped gracefully.
