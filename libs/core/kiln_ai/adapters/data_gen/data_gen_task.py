import json

from kiln_ai.adapters.prompt_builders import SimplePromptBuilder
from kiln_ai.datamodel import Project, Task
from pydantic import BaseModel

from .data_gen_prompts import (
    SAMPLE_GENERATION_PROMPT,
    TREE_GENERATION_PROMPT,
)


class DataGenCategoriesTaskInput(BaseModel):
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
        prompt_builder = SimplePromptBuilder(task=task)
        return cls(
            node_path=node_path,
            num_subtopics=num_subtopics,
            human_guidance=human_guidance,
            existing_topics=existing_topics,
            system_prompt=prompt_builder.build_prompt(),
        )


class DataGenCategoriesTaskOutput(BaseModel):
    subtopics: list[str]


class DataGenCategoriesTask(Task, parent_of={}):
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
        prompt_builder = SimplePromptBuilder(task=task)
        return cls(
            topic=topic,
            num_samples=num_samples,
            human_guidance=human_guidance,
            system_prompt=prompt_builder.build_prompt(),
        )


def list_json_schema_for_task(task: Task) -> str:
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

    return json.dumps(top_level_schema)


class DataGenSampleTask(Task, parent_of={}):
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
