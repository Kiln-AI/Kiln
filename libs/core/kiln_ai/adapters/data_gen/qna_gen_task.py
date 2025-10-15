import json

from pydantic import BaseModel

from kiln_ai.datamodel import Project, Task

from .data_gen_prompts import generate_qna_generation_prompt


class DataGenQnaTaskInput(BaseModel):
    kiln_data_gen_document_id: list[str]
    kiln_data_gen_part_text: list[str]
    kiln_data_gen_num_samples: int

    @classmethod
    def from_task(
        cls,
        task: Task,
        document_id: list[str] = [],
        part_text: list[str] = [],
        num_samples: int = 8,
    ) -> "DataGenQnaTaskInput":
        return cls(
            kiln_data_gen_document_id=document_id,
            kiln_data_gen_part_text=part_text,
            kiln_data_gen_num_samples=num_samples,
        )


def list_json_schema_for_task(task: Task) -> str:
    # Parse input schema for question field
    if task.input_json_schema:
        question_schema = json.loads(task.input_json_schema)
    else:
        question_schema = {"type": "string"}

    if task.output_json_schema:
        answer_schema = json.loads(task.output_json_schema)
    else:
        answer_schema = {"type": "string"}

    qna_pair_schema = {
        "type": "object",
        "properties": {
            "question": question_schema,
            "answer": answer_schema,
        },
        "required": ["question", "answer"],
    }

    list_schema = {
        "type": "array",
        "items": qna_pair_schema,
    }

    top_level_schema = {
        "type": "object",
        "properties": {
            "generated_qna_pairs": list_schema,
        },
        "required": ["generated_qna_pairs"],
    }

    return json.dumps(top_level_schema, ensure_ascii=False)


class DataGenQnaTask(Task, parent_of={}):
    def __init__(
        self,
        target_task: Task,
        guidance: str | None,
    ):
        # Keep the typechecker happy. We should make this optional.
        tmp_project = Project(name="DataGenQna")

        instruction = generate_qna_generation_prompt(guidance=guidance)

        super().__init__(
            name="DataGenQna",
            parent=tmp_project,
            description="A task which generates synthetic Q&A pairs from document content.",
            instruction=instruction,
            input_json_schema=json.dumps(DataGenQnaTaskInput.model_json_schema()),
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
