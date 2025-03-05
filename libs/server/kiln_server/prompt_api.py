from datetime import datetime

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel import BasePrompt, Prompt, PromptId
from pydantic import BaseModel

from kiln_server.task_api import task_from_id


def editable_prompt_from_id(project_id: str, task_id: str, prompt_id: str) -> Prompt:
    """
    Only custom prompts can be updated. Automatically frozen prompts can not be edited/deleted as they are required to be static by evals and other parts of the system.
    """
    parent_task = task_from_id(project_id, task_id)
    if not prompt_id.startswith("id::"):
        raise HTTPException(
            status_code=400,
            detail="Only custom prompts can be updated. Automatically frozen prompts can not be edited or deleted.",
        )
    id = prompt_id[4:]
    prompt = next((p for p in parent_task.prompts() if p.id == id), None)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


# This is a wrapper around the Prompt datamodel that adds an id field which represents the PromptID and not the data model ID.
class ApiPrompt(BasePrompt):
    id: PromptId
    created_at: datetime | None = None
    created_by: str | None = None


class PromptCreateRequest(BaseModel):
    name: str
    description: str | None = None
    prompt: str
    chain_of_thought_instructions: str | None = None


class PromptGenerator(BaseModel):
    id: str
    short_description: str
    description: str
    name: str
    chain_of_thought: bool


class PromptResponse(BaseModel):
    generators: list[PromptGenerator]
    prompts: list[ApiPrompt]


class PromptUpdateRequest(BaseModel):
    name: str
    description: str | None = None


def connect_prompt_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/task/{task_id}/prompt")
    async def create_prompt(
        project_id: str, task_id: str, prompt_data: PromptCreateRequest
    ) -> Prompt:
        parent_task = task_from_id(project_id, task_id)
        prompt = Prompt(
            parent=parent_task,
            name=prompt_data.name,
            description=prompt_data.description,
            prompt=prompt_data.prompt,
            chain_of_thought_instructions=prompt_data.chain_of_thought_instructions,
        )
        prompt.save_to_file()
        return prompt

    @app.get("/api/projects/{project_id}/task/{task_id}/prompts")
    async def get_prompts(project_id: str, task_id: str) -> PromptResponse:
        parent_task = task_from_id(project_id, task_id)

        prompts: list[ApiPrompt] = []
        for prompt in parent_task.prompts():
            properties = prompt.model_dump(exclude={"id"})
            prompts.append(ApiPrompt(id=f"id::{prompt.id}", **properties))

        # Add any task run config prompts to the list
        task_run_configs = parent_task.run_configs()
        for task_run_config in task_run_configs:
            if task_run_config.prompt:
                properties = task_run_config.prompt.model_dump(exclude={"id"})
                prompts.append(
                    ApiPrompt(
                        id=f"task_run_config::{project_id}::{task_id}::{task_run_config.id}",
                        **properties,
                    )
                )

        return PromptResponse(
            generators=_prompt_generators,
            prompts=prompts,
        )

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}")
    async def update_prompt(
        project_id: str, task_id: str, prompt_id: str, prompt_data: PromptUpdateRequest
    ) -> Prompt:
        prompt = editable_prompt_from_id(project_id, task_id, prompt_id)
        prompt.name = prompt_data.name
        prompt.description = prompt_data.description
        prompt.save_to_file()
        return prompt

    @app.delete("/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}")
    async def delete_prompt(project_id: str, task_id: str, prompt_id: str) -> None:
        prompt = editable_prompt_from_id(project_id, task_id, prompt_id)
        prompt.delete()


# User friendly descriptions of the prompt generators
_prompt_generators = [
    PromptGenerator(
        id="simple_prompt_builder",
        name="Basic (Zero Shot)",
        short_description="Includes the instructions and requirements from your task definition.",
        description="A basic prompt generator. It will include the instructions and requirements from your task definition. It won't include any examples from your runs (zero-shot).",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="few_shot_prompt_builder",
        name="Few-Shot",
        short_description="Includes up to 4 examples from your dataset.",
        description="A multi-shot prompt generator that includes up to 4 examples from your dataset (few-shot). It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="multi_shot_prompt_builder",
        name="Many-Shot",
        short_description="Includes up to 25 examples from your dataset.",
        description="A multi-shot prompt generator that includes up to 25 examples from your dataset (many-shot). It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="repairs_prompt_builder",
        name="Repair Multi-Shot",
        short_description="Includes examples from your dataset, including human feedback about mistakes and how to correct them.",
        description="A multi-shot prompt that will include up to 25 examples from your dataset. This prompt will use repaired examples to show 1) the generated content which had issues, 2) the human feedback about what was incorrect, 3) the corrected and approved content. This gives the LLM examples of common errors to avoid. It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="simple_chain_of_thought_prompt_builder",
        name="Chain of Thought",
        short_description="Gives the LLM time to 'think' before replying.",
        description="A chain of thought prompt generator that gives the LLM time to 'think' before replying. It will use the thinking_instruction from your task definition if it exists, or a standard 'step by step' instruction. The result will only include the final answer, not the 'thinking' tokens. The 'thinking' tokens will be available in the data model. It also includes the instructions and requirements from your task definition.",
        chain_of_thought=True,
    ),
    PromptGenerator(
        id="few_shot_chain_of_thought_prompt_builder",
        name="Chain of Thought - Few Shot",
        short_description="Combines our 'Chain of Thought' generator with our 'Few-Shot' generator.",
        description="Combines our 'Chain of Thought' generator with our 'Few-Shot' generator, for both the thinking and the few shot examples.",
        chain_of_thought=True,
    ),
    PromptGenerator(
        id="multi_shot_chain_of_thought_prompt_builder",
        name="Chain of Thought - Many Shot",
        short_description="Combines our 'Chain of Thought' generator with our 'Many-Shot' generator.",
        description="Combines our 'Chain of Thought' generator with our 'Many-Shot' generator, for both the thinking and the many shot examples.",
        chain_of_thought=True,
    ),
]
