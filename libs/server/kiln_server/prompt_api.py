from fastapi import FastAPI
from kiln_ai.datamodel import Prompt
from pydantic import BaseModel

from kiln_server.task_api import task_from_id


class PromptCreateRequest(BaseModel):
    name: str
    prompt: str
    chain_of_thought_instructions: str | None = None


class PromptGenerator(BaseModel):
    id: str
    ui_id: str
    short_description: str
    description: str
    name: str
    chain_of_thought: bool


class PromptResponse(BaseModel):
    generators: list[PromptGenerator]
    prompts: list[Prompt]


def connect_prompt_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/task/{task_id}/prompt")
    async def create_prompt(
        project_id: str, task_id: str, prompt_data: PromptCreateRequest
    ) -> Prompt:
        parent_task = task_from_id(project_id, task_id)
        prompt = Prompt(
            parent=parent_task,
            name=prompt_data.name,
            prompt=prompt_data.prompt,
            chain_of_thought_instructions=prompt_data.chain_of_thought_instructions,
        )
        prompt.save_to_file()
        return prompt

    @app.get("/api/projects/{project_id}/task/{task_id}/prompts")
    async def get_prompts(project_id: str, task_id: str) -> PromptResponse:
        parent_task = task_from_id(project_id, task_id)

        return PromptResponse(
            generators=_prompt_generators,
            prompts=parent_task.prompts(),
        )


_prompt_generators = [
    PromptGenerator(
        id="basic",
        ui_id="simple_prompt_builder",
        name="Basic (Zero Shot)",
        short_description="Includes the instructions and requirements from your task definition.",
        description="A basic prompt generator. It will include the instructions and requirements from your task definition. It won't include any examples from your runs (zero-shot).",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="few_shot",
        ui_id="few_shot_prompt_builder",
        name="Few-Shot",
        short_description="Includes up to 4 examples from your dataset.",
        description="A multi-shot prompt generator that includes up to 4 examples from your dataset (few-shot). It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="many_shot",
        ui_id="multi_shot_prompt_builder",
        name="Many-Shot",
        short_description="Includes up to 25 examples from your dataset.",
        description="A multi-shot prompt generator that includes up to 25 examples from your dataset (many-shot). It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="repairs",
        ui_id="repairs_prompt_builder",
        name="Repair Multi-Shot",
        short_description="Includes examples from your dataset, including human feedback about mistakes and how to correct them.",
        description="A multi-shot prompt that will include up to 25 examples from your dataset. This prompt will use repaired examples to show 1) the generated content which had issues, 2) the human feedback about what was incorrect, 3) the corrected and approved content. This gives the LLM examples of common errors to avoid. It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="simple_chain_of_thought",
        ui_id="simple_chain_of_thought_prompt_builder",
        name="Chain of Thought",
        short_description="Gives the LLM time to 'think' before replying.",
        description="A chain of thought prompt generator that gives the LLM time to 'think' before replying. It will use the thinking_instruction from your task definition if it exists, or a standard 'step by step' instruction. The result will only include the final answer, not the 'thinking' tokens. The 'thinking' tokens will be available in the data model. It also includes the instructions and requirements from your task definition.",
        chain_of_thought=True,
    ),
    PromptGenerator(
        id="few_shot_chain_of_thought",
        ui_id="few_shot_chain_of_thought_prompt_builder",
        name="Chain of Thought - Few Shot",
        short_description="Combines our 'Chain of Thought' generator with our 'Few-Shot' generator.",
        description="Combines our 'Chain of Thought' generator with our 'Few-Shot' generator, for both the thinking and the few shot examples.",
        chain_of_thought=True,
    ),
    PromptGenerator(
        id="multi_shot_chain_of_thought",
        ui_id="multi_shot_chain_of_thought_prompt_builder",
        name="Chain of Thought - Many Shot",
        short_description="Combines our 'Chain of Thought' generator with our 'Many-Shot' generator.",
        description="Combines our 'Chain of Thought' generator with our 'Many-Shot' generator, for both the thinking and the many shot examples.",
        chain_of_thought=True,
    ),
]
