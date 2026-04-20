from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.adapters.prompt_builders import CustomExamplePromptBuilder, PromptExample
from kiln_ai.datamodel import BasePrompt, Prompt, PromptId
from kiln_ai.datamodel.prompt_type import prompt_type_label
from pydantic import BaseModel, Field

from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    agent_policy_require_approval,
)


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
    """A prompt with its PromptId and metadata."""

    id: PromptId = Field(description="The prompt ID used to reference this prompt.")
    type: str = Field(
        description="The type label for this prompt (e.g. 'Custom', 'Fine-Tune', 'Frozen', 'Few-Shot')."
    )
    created_at: datetime | None = Field(
        default=None, description="When the prompt was created."
    )
    created_by: str | None = Field(
        default=None, description="The user who created the prompt."
    )


class PromptCreateRequest(BaseModel):
    """Request to create a new prompt."""

    generator_id: str | None = Field(
        default=None, description="The generator ID if this prompt was auto-generated."
    )
    name: str = Field(description="The name of the prompt.")
    description: str | None = Field(
        default=None, description="A description of the prompt."
    )
    prompt: str = Field(description="The prompt text.")
    chain_of_thought_instructions: str | None = Field(
        default=None,
        description="Chain of thought instructions to include in the prompt.",
    )


class PromptGenerator(BaseModel):
    """A built-in prompt generator that can construct prompts from a task."""

    id: str = Field(description="The unique identifier of the generator.")
    short_description: str = Field(description="A brief description of the generator.")
    description: str = Field(description="A detailed description of the generator.")
    name: str = Field(description="The display name of the generator.")
    chain_of_thought: bool = Field(
        description="Whether the generator includes chain of thought instructions."
    )


class PromptResponse(BaseModel):
    """The available prompt generators and saved prompts for a task."""

    generators: list[PromptGenerator] = Field(
        description="The available prompt generators."
    )
    prompts: list[ApiPrompt] = Field(description="The saved prompts for the task.")


class PromptUpdateRequest(BaseModel):
    """Request to update a prompt."""

    name: str = Field(description="The updated name.")
    description: str | None = Field(
        default=None, description="The updated description."
    )


class FewShotExample(BaseModel):
    """An input/output example for few-shot prompting."""

    input: str = Field(description="The example input.")
    output: str = Field(description="The example output.")


class BuildPromptRequest(BaseModel):
    """Request to build a prompt from examples."""

    examples: list[FewShotExample] = Field(
        default=[], description="Few-shot examples to include in the prompt."
    )


class BuildPromptResponse(BaseModel):
    """Response containing a fully constructed prompt with examples."""

    prompt: str = Field(description="The generated prompt text.")


def connect_prompt_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/prompts",
        summary="Create Prompt",
        tags=["Prompts"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_prompt(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        prompt_data: PromptCreateRequest,
    ) -> Prompt:
        parent_task = task_from_id(project_id, task_id)
        prompt = Prompt(
            parent=parent_task,
            generator_id=prompt_data.generator_id,
            name=prompt_data.name,
            description=prompt_data.description,
            prompt=prompt_data.prompt,
            chain_of_thought_instructions=prompt_data.chain_of_thought_instructions,
        )
        prompt.save_to_file()
        return prompt

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/prompts",
        summary="List Prompts",
        tags=["Prompts"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_prompts(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> PromptResponse:
        parent_task = task_from_id(project_id, task_id)

        prompts: list[ApiPrompt] = []
        for prompt in parent_task.prompts():
            prompt_id = f"id::{prompt.id}"
            properties = prompt.model_dump(exclude={"id"})
            prompts.append(
                ApiPrompt(
                    id=prompt_id,
                    type=prompt_type_label(prompt_id, prompt.generator_id),
                    **properties,
                )
            )

        # Add any task run config prompts to the list
        task_run_configs = parent_task.run_configs()
        for task_run_config in task_run_configs:
            if task_run_config.prompt:
                prompt_id = (
                    f"task_run_config::{project_id}::{task_id}::{task_run_config.id}"
                )
                properties = task_run_config.prompt.model_dump(exclude={"id"})
                prompts.append(
                    ApiPrompt(
                        id=prompt_id,
                        type=prompt_type_label(
                            prompt_id, task_run_config.prompt.generator_id
                        ),
                        created_at=task_run_config.created_at,
                        **properties,
                    )
                )

        return PromptResponse(
            generators=prompt_generators,
            prompts=prompts,
        )

    @app.patch(
        "/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}",
        summary="Update Prompt",
        tags=["Prompts"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to edit prompt? Ensure you backup your project before allowing agentic edits."
        ),
    )
    async def update_prompt(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        prompt_id: Annotated[
            str, Path(description="The unique identifier of the prompt.")
        ],
        prompt_data: PromptUpdateRequest,
    ) -> ApiPrompt:
        prompt = editable_prompt_from_id(project_id, task_id, prompt_id)
        prompt.name = prompt_data.name
        prompt.description = prompt_data.description
        prompt.save_to_file()
        api_prompt_id = f"id::{prompt.id}"
        properties = prompt.model_dump(exclude={"id"})
        return ApiPrompt(
            id=api_prompt_id,
            type=prompt_type_label(api_prompt_id, prompt.generator_id),
            **properties,
        )

    @app.delete(
        "/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}",
        summary="Delete Prompt",
        tags=["Prompts"],
        openapi_extra=DENY_AGENT,
    )
    async def delete_prompt(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        prompt_id: Annotated[
            str, Path(description="The unique identifier of the prompt.")
        ],
    ) -> None:
        prompt = editable_prompt_from_id(project_id, task_id, prompt_id)
        prompt.delete()

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/build_prompt_with_examples",
        summary="Build Prompt With Examples",
        tags=["Prompts"],
        openapi_extra=ALLOW_AGENT,
    )
    async def build_prompt_with_examples(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        request: BuildPromptRequest,
    ) -> BuildPromptResponse:
        """Build a prompt with task instruction, requirements, and optional custom examples.

        Uses the same formatting as the FewShotPromptBuilder but with user-provided examples.
        """
        task = task_from_id(project_id, task_id)
        examples = [
            PromptExample(input=e.input, output=e.output) for e in request.examples
        ]
        builder = CustomExamplePromptBuilder(task, examples)
        prompt = builder.build_prompt(include_json_instructions=False)
        return BuildPromptResponse(prompt=prompt)


# User friendly descriptions of the prompt generators
prompt_generators = [
    PromptGenerator(
        id="simple_prompt_builder",
        name="Basic (Zero Shot)",
        short_description="Just the prompt, no examples.",
        description="A basic prompt generator. It will include the instructions from your task definition. It won't include any examples from your runs (zero-shot).",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="few_shot_prompt_builder",
        name="Few-Shot",
        short_description="Includes up to 4 examples.",
        description="A multi-shot prompt generator that includes up to 4 examples from your dataset (few-shot). It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="multi_shot_prompt_builder",
        name="Many-Shot",
        short_description="Includes up to 25 examples.",
        description="A multi-shot prompt generator that includes up to 25 examples from your dataset (many-shot). It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="repairs_prompt_builder",
        name="Repair Multi-Shot",
        short_description="With examples of human repairs.",
        description="A multi-shot prompt that will include up to 25 examples from your dataset. This prompt will use repaired examples to show 1) the generated content which had issues, 2) the human feedback about what was incorrect, 3) the corrected and approved content. This gives the LLM examples of common errors to avoid. It also includes the instructions and requirements from your task definition.",
        chain_of_thought=False,
    ),
    PromptGenerator(
        id="simple_chain_of_thought_prompt_builder",
        name="Chain of Thought",
        short_description="Give the LLM time to 'think'.",
        description="A chain of thought prompt generator that gives the LLM time to 'think' before replying. It will use the thinking_instruction from your task definition if it exists, or a standard 'step by step' instruction. The result will only include the final answer, not the 'thinking' tokens. The 'thinking' tokens will be available in the data model. It also includes the instructions and requirements from your task definition.",
        chain_of_thought=True,
    ),
    PromptGenerator(
        id="few_shot_chain_of_thought_prompt_builder",
        name="Chain of Thought + Few Shot",
        short_description="Combines CoT and few-shot.",
        description="Combines our 'Chain of Thought' generator with our 'Few-Shot' generator, for both the thinking and the few shot examples.",
        chain_of_thought=True,
    ),
    PromptGenerator(
        id="multi_shot_chain_of_thought_prompt_builder",
        name="Chain of Thought + Many Shot",
        short_description="Combines CoT and many-shot.",
        description="Combines our 'Chain of Thought' generator with our 'Many-Shot' generator, for both the thinking and the many shot examples.",
        chain_of_thought=True,
    ),
]
