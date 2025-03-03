import json
from typing import Type

from pydantic import BaseModel, Field

from kiln_ai.adapters.prompt_builders import (
    BasePromptBuilder,
    SavedPromptBuilder,
    prompt_builder_from_id,
)
from kiln_ai.datamodel import Priority, Project, Task, TaskRequirement, TaskRun


# TODO add evaluator rating
class RepairTaskInput(BaseModel):
    original_prompt: str
    original_input: str
    original_output: str
    evaluator_feedback: str = Field(
        min_length=1,
        description="Feedback from an evaluator on how to repair the task run.",
    )


class RepairTaskRun(Task, parent_of={}):
    def __init__(self, original_task: Task):
        # Keep the typechecker happy
        tmp_project = Project(name="Repair")
        super().__init__(
            name="Repair",
            parent=tmp_project,
            description="Repair a task run, given feedback from an evaluator about how the response can be improved.",
            instruction="You are an assistant which helps improve output from another assistant (original assistant). You'll be provided a task that the original assistant executed (prompt), \
the input it was given, and the output it generated. An evaluator has determined that the output it generated did not satisfy the task and should be improved. The evaluator will provide \
feedback describing what should be improved. Your job is to understand the evaluator's feedback and improve the response.",
            requirements=[
                TaskRequirement(
                    name="Follow Eval Feedback",
                    instruction="The evaluator's feedback is the most important thing to consider. If it conflicts with the original task instruction or prompt, prioritize the evaluator's feedback.",
                    priority=Priority.p0,
                )
            ],
            input_json_schema=json.dumps(RepairTaskInput.model_json_schema()),
            output_json_schema=original_task.output_json_schema,
        )

    @classmethod
    def _original_prompt(cls, run: TaskRun, task: Task) -> str:
        if run.output.source is None or run.output.source.properties is None:
            raise ValueError("No source properties found")

        # Get the prompt builder id. Need the second check because we used to store this in a prompt_builder_name field, so loading legacy runs will need this.
        prompt_id = run.output.source.properties.get(
            "prompt_id"
        ) or run.output.source.properties.get("prompt_builder_name", None)
        if prompt_id is not None and isinstance(prompt_id, str):
            prompt_builder = prompt_builder_from_id(prompt_id, task)
            if isinstance(prompt_builder, BasePromptBuilder):
                return prompt_builder.build_prompt(include_json_instructions=False)

        raise ValueError(f"Prompt builder '{prompt_id}' is not a valid prompt builder")

    @classmethod
    def build_repair_task_input(
        cls, original_task: Task, task_run: TaskRun, evaluator_feedback: str
    ) -> RepairTaskInput:
        original_prompt = cls._original_prompt(task_run, original_task)
        return RepairTaskInput(
            original_prompt=original_prompt,
            original_input=task_run.input,
            original_output=task_run.output.output,
            evaluator_feedback=evaluator_feedback,
        )
