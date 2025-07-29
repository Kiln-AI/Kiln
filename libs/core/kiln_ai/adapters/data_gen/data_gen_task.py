import json
from typing import Literal

from pydantic import BaseModel

from kiln_ai.adapters.prompt_builders import SimplePromptBuilder
from kiln_ai.datamodel import Project, Task

from .data_gen_prompts import (
    generate_sample_generation_prompt,
    generate_topic_tree_prompt,
)


class DataGenCategoriesTaskInput(BaseModel):
    """Input model for generating categories/subtopics.

    Note: the field names are very verbose to avoid accidental conflicts with the system prompt or user guidance.

    Attributes:
        kiln_data_gen_topic_path: List of strings representing the hierarchical path to current node
        kiln_data_gen_system_prompt: System prompt to guide the AI generation
        kiln_data_gen_num_subtopics: Number of subtopics to generate
        kiln_data_gen_existing_topics: Optional list of existing topics to avoid duplication
    """

    kiln_data_gen_topic_path: list[str]
    kiln_data_gen_system_prompt: str
    kiln_data_gen_num_subtopics: int
    kiln_data_gen_existing_topics: list[str] | None = None

    @classmethod
    def from_task(
        cls,
        task: Task,
        node_path: list[str] = [],
        num_subtopics: int = 6,
        existing_topics: list[str] | None = None,
    ) -> "DataGenCategoriesTaskInput":
        """Create a DataGenCategoriesTaskInput instance from a Task.

        Args:
            task: The source Task object
            node_path: Path to current node in topic hierarchy
            num_subtopics: Number of subtopics to generate
            existing_topics: Optional list of existing topics

        Returns:
            A new DataGenCategoriesTaskInput instance
        """
        prompt_builder = SimplePromptBuilder(task=task)
        return cls(
            kiln_data_gen_topic_path=node_path,
            kiln_data_gen_num_subtopics=num_subtopics,
            kiln_data_gen_existing_topics=existing_topics,
            kiln_data_gen_system_prompt=prompt_builder.build_prompt(
                include_json_instructions=False
            ),
        )


class DataGenCategoriesTaskOutput(BaseModel):
    """Output model for generated categories/subtopics.

    Attributes:
        subtopics: List of generated subtopic strings
    """

    subtopics: list[str]


class DataGenCategoriesTask(Task, parent_of={}):
    """Task for generating hierarchical categories/subtopics.

    Generates synthetic data categories which can be used to generate
    training data for model learning.
    """

    def __init__(self, gen_type: Literal["training", "eval"], guidance: str | None):
        # Keep the typechecker happy. We should make this optional.
        tmp_project = Project(name="DataGen")

        instruction = generate_topic_tree_prompt(gen_type=gen_type, guidance=guidance)

        super().__init__(
            name="DataGen",
            parent=tmp_project,
            description="A task which generates synthetic data categories, which in turn are used to generate training data for a model to learn from.",
            instruction=instruction,
            input_json_schema=json.dumps(
                DataGenCategoriesTaskInput.model_json_schema()
            ),
            output_json_schema=json.dumps(
                DataGenCategoriesTaskOutput.model_json_schema()
            ),
        )


class DataGenSampleTaskInput(BaseModel):
    """Input model for generating data samples for a kiln task.

    Note: the field names are very verbose to avoid accidental conflicts with the system prompt or user guidance.

    Attributes:
        kiln_data_gen_topic_path: List of strings representing the topic path
        kiln_data_gen_system_prompt: System prompt to guide the AI generation
        kiln_data_gen_num_samples: Number of samples to generate
    """

    kiln_data_gen_topic_path: list[str]
    kiln_data_gen_system_prompt: str
    kiln_data_gen_num_samples: int

    @classmethod
    def from_task(
        cls,
        task: Task,
        topic: list[str] = [],
        num_samples: int = 8,
    ) -> "DataGenSampleTaskInput":
        """Create a DataGenSampleTaskInput instance from a Task.

        Args:
            task: The source Task object
            topic: Topic path for sample generation
            num_samples: Number of samples to generate
            human_guidance: Optional guidance for generation

        Returns:
            A new DataGenSampleTaskInput instance
        """
        prompt_builder = SimplePromptBuilder(task=task)
        return cls(
            kiln_data_gen_topic_path=topic,
            kiln_data_gen_num_samples=num_samples,
            kiln_data_gen_system_prompt=prompt_builder.build_prompt(
                include_json_instructions=False
            ),
        )


def list_json_schema_for_task(task: Task) -> str:
    """Generate a JSON schema for a list of task inputs (json schema)

    Args:
        task: Task object whose input schema will be used

    Returns:
        JSON string representing the schema for a list of task inputs
    """
    if task.input_json_schema:
        items_schema = json.loads(task.input_json_schema)
    else:
        items_schema = {"type": "string"}

    list_schema = {
        "type": "array",
        "items": items_schema,
    }

    top_level_schema = {
        "type": "object",
        "properties": {
            "generated_samples": list_schema,
        },
        "required": ["generated_samples"],
    }

    return json.dumps(top_level_schema, ensure_ascii=False)


class DataGenSampleTask(Task, parent_of={}):
    """Task for generating data samples for a given topic.

    Generates synthetic data samples based on provided topics and subtopics.
    """

    def __init__(
        self,
        target_task: Task,
        gen_type: Literal["training", "eval"],
        guidance: str | None,
    ):
        # Keep the typechecker happy. We should make this optional.
        tmp_project = Project(name="DataGenSample")

        instruction = generate_sample_generation_prompt(
            gen_type=gen_type, guidance=guidance
        )

        super().__init__(
            name="DataGenSample",
            parent=tmp_project,
            description="A task which generates synthetic data samples for a given topic (and optional subtopic).",
            instruction=instruction,
            input_json_schema=json.dumps(DataGenSampleTaskInput.model_json_schema()),
            output_json_schema=list_json_schema_for_task(target_task),
        )


def wrap_task_with_guidance(original_instruction: str, guidance: str) -> str:
    """Wrap the original instruction with human guidance.

    Args:
        original_instruction: The original instruction to wrap
        guidance: The human guidance to wrap the instruction with
    """
    return f"""{original_instruction}

# Special Instructions

The above instructions are the original instructions for this task. For this execution, we've been given additional instructions. Follow both, but prioritize the additional instructions when they conflict. The additional instructions are:
<additional_instructions>
{guidance}
</additional_instructions>
"""
