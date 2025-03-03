import json

from pydantic import BaseModel

from kiln_ai.adapters.prompt_builders import SimplePromptBuilder
from kiln_ai.datamodel import Project, Task

from .data_gen_prompts import (
    SAMPLE_GENERATION_PROMPT,
    TREE_GENERATION_PROMPT,
)


class DataGenCategoriesTaskInput(BaseModel):
    """Input model for generating categories/subtopics.

    Attributes:
        node_path: List of strings representing the hierarchical path to current node
        system_prompt: System prompt to guide the AI generation
        num_subtopics: Number of subtopics to generate
        human_guidance: Optional human guidance to influence generation
        existing_topics: Optional list of existing topics to avoid duplication
    """

    node_path: list[str]
    system_prompt: str
    num_subtopics: int
    human_guidance: str | None = None
    existing_topics: list[str] | None = None

    @classmethod
    def from_task(
        cls,
        task: Task,
        node_path: list[str] = [],
        num_subtopics: int = 6,
        human_guidance: str | None = None,
        existing_topics: list[str] | None = None,
    ) -> "DataGenCategoriesTaskInput":
        """Create a DataGenCategoriesTaskInput instance from a Task.

        Args:
            task: The source Task object
            node_path: Path to current node in topic hierarchy
            num_subtopics: Number of subtopics to generate
            human_guidance: Optional guidance for generation
            existing_topics: Optional list of existing topics

        Returns:
            A new DataGenCategoriesTaskInput instance
        """
        prompt_builder = SimplePromptBuilder(task=task)
        return cls(
            node_path=node_path,
            num_subtopics=num_subtopics,
            human_guidance=human_guidance,
            existing_topics=existing_topics,
            system_prompt=prompt_builder.build_prompt(include_json_instructions=False),
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

    def __init__(self):
        # Keep the typechecker happy. TODO: shouldn't need this or parent_of above.
        tmp_project = Project(name="DataGen")
        super().__init__(
            name="DataGen",
            parent=tmp_project,
            description="A task which generates synthetic data categories, which in turn are used to generate training data for a model to learn from.",
            instruction=TREE_GENERATION_PROMPT,
            input_json_schema=json.dumps(
                DataGenCategoriesTaskInput.model_json_schema()
            ),
            output_json_schema=json.dumps(
                DataGenCategoriesTaskOutput.model_json_schema()
            ),
        )


class DataGenSampleTaskInput(BaseModel):
    """Input model for generating data samples for a kiln task.

    Attributes:
        topic: List of strings representing the topic path
        system_prompt: System prompt to guide the AI generation
        num_samples: Number of samples to generate
        human_guidance: Optional human guidance to influence generation
    """

    topic: list[str]
    system_prompt: str
    num_samples: int
    human_guidance: str | None = None

    @classmethod
    def from_task(
        cls,
        task: Task,
        topic: list[str] = [],
        num_samples: int = 8,
        human_guidance: str | None = None,
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
            topic=topic,
            num_samples=num_samples,
            human_guidance=human_guidance,
            system_prompt=prompt_builder.build_prompt(include_json_instructions=False),
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

    def __init__(self, target_task: Task, num_samples: int = 8):
        # Keep the typechecker happy. TODO: shouldn't need this or parent_of above.
        tmp_project = Project(name="DataGenSample")
        super().__init__(
            name="DataGenSample",
            parent=tmp_project,
            description="A task which generates synthetic data samples for a given topic (and optional subtopic).",
            instruction=SAMPLE_GENERATION_PROMPT,
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
