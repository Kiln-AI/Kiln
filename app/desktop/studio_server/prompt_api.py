from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.prompt_builders import prompt_builder_from_id
from kiln_ai.datamodel import PromptId
from kiln_server.task_api import task_from_id
from pydantic import BaseModel


class PromptApiResponse(BaseModel):
    prompt: str
    prompt_id: PromptId


def connect_prompt_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_id}")
    async def generate_prompt(
        project_id: str,
        task_id: str,
        prompt_id: PromptId,
    ) -> PromptApiResponse:
        task = task_from_id(project_id, task_id)

        try:
            prompt_builder = prompt_builder_from_id(prompt_id, task)
            prompt = prompt_builder.build_prompt_for_ui()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        return PromptApiResponse(
            prompt=prompt,
            prompt_id=prompt_id,
        )
