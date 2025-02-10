from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.prompt_builders import prompt_builder_from_ui_name
from kiln_server.task_api import task_from_id
from pydantic import BaseModel


class PromptApiResponse(BaseModel):
    prompt: str
    prompt_builder_name: str
    ui_generator_name: str


def connect_prompt_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_generator}")
    async def generate_prompt(
        project_id: str, task_id: str, prompt_generator: str
    ) -> PromptApiResponse:
        task = task_from_id(project_id, task_id)

        try:
            prompt_builder = prompt_builder_from_ui_name(prompt_generator, task)
            prompt = prompt_builder.build_prompt_for_ui()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        return PromptApiResponse(
            prompt=prompt,
            prompt_builder_name=prompt_builder.__class__.prompt_builder_name(),
            ui_generator_name=prompt_generator,
        )
