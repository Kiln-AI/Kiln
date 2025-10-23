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

    # Extraction lists schema - domain-agnostic
    extraction_lists_schema = {
        "type": "object",
        "properties": {
            "named_entities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all people, organizations, or teams",
            },
            "locations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all places, buildings, facilities, or regions",
            },
            "events": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all meetings, incidents, deployments, actions, or milestones",
            },
            "concepts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all themes, ideas, goals, problems, solutions, or policies",
            },
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all physical items, parts, products, vehicles, equipment, or assets",
            },
            "documents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all records, files, agreements, reports, or forms",
            },
            "systems": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all technical components, software, processes, APIs, or architectures",
            },
        },
        "required": [
            "named_entities",
            "locations",
            "events",
            "concepts",
            "objects",
            "documents",
            "systems",
        ],
    }

    # Edge verification schema - single edge only
    edge_verification_schema = {
        "type": "object",
        "properties": {
            "edge_used": {"type": "string"},
        },
        "required": ["edge_used"],
    }

    # Knowledge graph schema
    knowledge_graph_schema = {
        "type": "object",
        "properties": {
            "nodes": {"type": "array", "items": {"type": "string"}},
            "edges": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["nodes", "edges"],
    }

    # Q&A pair schema with edge verification
    qna_pair_schema = {
        "type": "object",
        "properties": {
            "edge_verification": edge_verification_schema,
            "question": question_schema,
            "answer": answer_schema,
        },
        "required": ["edge_verification", "question", "answer"],
    }

    list_schema = {
        "type": "array",
        "items": qna_pair_schema,
    }

    # Top level schema
    top_level_schema = {
        "type": "object",
        "properties": {
            "extraction_lists": extraction_lists_schema,
            "knowledge_graph": knowledge_graph_schema,
            "generated_qna_pairs": list_schema,
        },
        "required": ["extraction_lists", "knowledge_graph", "generated_qna_pairs"],
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
