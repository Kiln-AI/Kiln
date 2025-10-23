import json

import pytest

from kiln_ai.adapters.data_gen.qna_gen_task import (
    DataGenQnaTask,
    DataGenQnaTaskInput,
    list_json_schema_for_task,
)
from kiln_ai.datamodel import Project, Task


@pytest.fixture
def base_task():
    project = Project(name="TestProject")
    return Task(
        name="QnA Test",
        parent=project,
        description="Answer questions about documents",
        instruction="Answer questions about documents",
        requirements=[],
    )


@pytest.fixture
def structured_task():
    project = Project(name="TestProject")
    return Task(
        name="Structured QnA Test",
        parent=project,
        description="Answer questions with structured input/output",
        instruction="Answer questions with structured input/output",
        requirements=[],
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["question", "context"],
            }
        ),
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["answer", "confidence"],
            }
        ),
    )


def test_data_gen_qna_task_input_initialization(base_task):
    # Arrange
    document_name = "doc1"
    part_text = ["Content 1", "Content 2"]
    num_samples = 5

    # Act
    input_model = DataGenQnaTaskInput.from_task(
        task=base_task,
        document_name=document_name,
        part_text=part_text,
        num_samples=num_samples,
    )

    # Assert
    assert input_model.kiln_data_gen_document_name == document_name
    assert input_model.kiln_data_gen_part_text == part_text
    assert input_model.kiln_data_gen_num_samples == num_samples


def test_data_gen_qna_task_input_default_values(base_task):
    # Act
    input_model = DataGenQnaTaskInput.from_task(task=base_task)

    # Assert
    assert input_model.kiln_data_gen_num_samples == 8
    assert input_model.kiln_data_gen_document_name == ""
    assert input_model.kiln_data_gen_part_text == []


def test_data_gen_qna_task_initialization(base_task):
    # Act
    task = DataGenQnaTask(target_task=base_task, guidance="Test guidance")

    # Assert
    assert task.name == "DataGenQna"
    assert isinstance(task.parent, Project)
    assert task.description is not None
    assert task.instruction is not None
    assert isinstance(task.input_json_schema, str)
    assert isinstance(task.output_json_schema, str)
    assert "Test guidance" in task.instruction


def test_list_json_schema_for_task_without_schemas(base_task):
    # Act
    schema = list_json_schema_for_task(base_task)
    parsed_schema = json.loads(schema)

    # Assert
    assert parsed_schema["type"] == "object"
    generated_qna_pairs_schema = parsed_schema["properties"]["generated_qna_pairs"]
    assert generated_qna_pairs_schema["type"] == "array"

    # Check QnA pair structure
    qna_pair_schema = generated_qna_pairs_schema["items"]
    assert qna_pair_schema["type"] == "object"
    assert qna_pair_schema["properties"]["question"]["type"] == "string"
    assert qna_pair_schema["properties"]["answer"]["type"] == "string"
    assert set(qna_pair_schema["required"]) == {"question", "answer"}


def test_list_json_schema_for_task_with_structured_schemas(structured_task):
    # Act
    schema = list_json_schema_for_task(structured_task)
    parsed_schema = json.loads(schema)

    # Assert
    assert parsed_schema["type"] == "object"
    generated_qna_pairs_schema = parsed_schema["properties"]["generated_qna_pairs"]
    assert generated_qna_pairs_schema["type"] == "array"

    # Check QnA pair structure with structured schemas
    qna_pair_schema = generated_qna_pairs_schema["items"]
    assert qna_pair_schema["type"] == "object"

    # Question should match input schema
    question_schema = qna_pair_schema["properties"]["question"]
    assert question_schema["type"] == "object"
    assert "question" in question_schema["properties"]
    assert "context" in question_schema["properties"]

    # Answer should match output schema
    answer_schema = qna_pair_schema["properties"]["answer"]
    assert answer_schema["type"] == "object"
    assert "answer" in answer_schema["properties"]
    assert "confidence" in answer_schema["properties"]

    assert set(qna_pair_schema["required"]) == {"question", "answer"}


def test_list_json_schema_for_task_with_mixed_schemas():
    project = Project(name="TestProject")
    task = Task(
        name="Mixed Schema Test",
        parent=project,
        description="Test with input schema but no output schema",
        instruction="Test instruction",
        requirements=[],
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }
        ),
        # No output_json_schema
    )

    # Act
    schema = list_json_schema_for_task(task)
    parsed_schema = json.loads(schema)

    # Assert
    qna_pair_schema = parsed_schema["properties"]["generated_qna_pairs"]["items"]

    # Question should use input schema
    question_schema = qna_pair_schema["properties"]["question"]
    assert question_schema["type"] == "object"
    assert "query" in question_schema["properties"]

    # Answer should default to string
    answer_schema = qna_pair_schema["properties"]["answer"]
    assert answer_schema["type"] == "string"
