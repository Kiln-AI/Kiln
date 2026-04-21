from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.adapters.prompt_builders import prompt_builder_from_id
from kiln_ai.datamodel import PromptId
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT
from pydantic import BaseModel


class PromptApiResponse(BaseModel):
    prompt: str
    prompt_id: PromptId
    chain_of_thought_instructions: str | None = None


def connect_prompt_api(app: FastAPI):
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}",
        tags=["Prompts"],
        openapi_extra=ALLOW_AGENT,
    )
    async def generate_prompt(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        prompt_id: Annotated[
            PromptId, Path(description="The prompt generator ID to use.")
        ],
    ) -> PromptApiResponse:
        task = task_from_id(project_id, task_id)

        try:
            prompt_builder = prompt_builder_from_id(prompt_id, task)
            # Return the base prompt without thinking instructions appended so
            # the UI can render the chain of thought as a separate, editable field.
            prompt = prompt_builder.build_prompt(include_json_instructions=False)
            cot_prompt = prompt_builder.chain_of_thought_prompt()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        return PromptApiResponse(
            prompt=prompt,
            prompt_id=prompt_id,
            chain_of_thought_instructions=cot_prompt,
        )
