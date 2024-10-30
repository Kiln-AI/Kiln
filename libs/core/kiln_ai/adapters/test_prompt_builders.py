import json

import pytest

from kiln_ai.adapters.base_adapter import AdapterInfo, BaseAdapter
from kiln_ai.adapters.prompt_builders import (
    FewShotPromptBuilder,
    MultiShotPromptBuilder,
    RepairsPromptBuilder,
    SimplePromptBuilder,
    prompt_builder_from_ui_name,
)
from kiln_ai.adapters.test_prompt_adaptors import build_test_task
from kiln_ai.adapters.test_structured_output import build_structured_output_test_task
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskOutputRating,
    TaskRun,
)


def test_simple_prompt_builder(tmp_path):
    task = build_test_task(tmp_path)
    builder = SimplePromptBuilder(task=task)
    input = "two plus two"
    prompt = builder.build_prompt()
    assert (
        "You are an assistant which performs math tasks provided in plain text."
        in prompt
    )

    assert "1) " + task.requirements[0].instruction in prompt
    assert "2) " + task.requirements[1].instruction in prompt
    assert "3) " + task.requirements[2].instruction in prompt

    user_msg = builder.build_user_message(input)
    assert input in user_msg
    assert input not in prompt


class MockAdapter(BaseAdapter):
    def adapter_specific_instructions(self) -> str | None:
        return "You are a mock, send me the response!"

    def _run(self, input: str) -> str:
        return "mock response"

    def adapter_info(self) -> AdapterInfo:
        return AdapterInfo(
            adapter_name="mock_adapter",
            model_name="mock_model",
            model_provider="mock_provider",
        )


def test_simple_prompt_builder_structured_output(tmp_path):
    task = build_structured_output_test_task(tmp_path)
    builder = SimplePromptBuilder(task=task)
    input = "Cows"
    prompt = builder.build_prompt()
    assert "You are an assistant which tells a joke, given a subject." in prompt

    # check adapter instructions are included
    run_adapter = MockAdapter(task, prompt_builder=builder)
    assert "You are a mock, send me the response!" in run_adapter.build_prompt()

    user_msg = builder.build_user_message(input)
    assert input in user_msg
    assert input not in prompt


@pytest.fixture
def task_with_examples(tmp_path):
    # Create a project and task hierarchy
    project = Project(name="Test Project", path=(tmp_path / "test_project.kiln"))
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="You are an assistant which tells a joke, given a subject.",
        parent=project,
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                },
                "required": ["subject"],
            }
        ),
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"joke": {"type": "string"}},
                "required": ["joke"],
            }
        ),
    )
    task.save_to_file()

    check_example_outputs(task, 0)

    # Create an task input, but with no output
    e1 = TaskRun(
        input='{"subject": "Cows"}',
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output='{"joke": "Moo I am a cow joke."}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
    )
    e1.save_to_file()

    ## still zero since not fixed and not rated highly
    check_example_outputs(task, 0)

    e1.output.rating = TaskOutputRating(value=4)
    e1.save_to_file()
    # Now that it's highly rated, it should be included
    check_example_outputs(task, 1)

    # Test with repaired output (highest priority)
    e1 = TaskRun(
        input='{"subject": "Cows"}',
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output='{"joke": "Moo I am a cow joke."}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
        repair_instructions="Fix the joke",
        repaired_output=TaskOutput(
            output='{"joke": "Why did the cow cross the road? To get to the udder side!"}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "jane_doe"},
            ),
        ),
    )
    e1.save_to_file()
    check_example_outputs(task, 1)

    # Test with high-quality output (second priority)
    e2 = TaskRun(
        input='{"subject": "Dogs"}',
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output='{"joke": "Why did the dog get a job? He wanted to be a collar-ary!"}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            rating=TaskOutputRating(value=4, reason="Good pun"),
        ),
    )
    e2.save_to_file()
    check_example_outputs(task, 2)

    # Test sorting by rating value
    e3 = TaskRun(
        input='{"subject": "Cats"}',
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output='{"joke": "Why don\'t cats play poker in the jungle? Too many cheetahs!"}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            rating=TaskOutputRating(value=5, reason="Excellent joke"),
        ),
    )
    e3.save_to_file()
    check_example_outputs(task, 3)
    return task


def test_multi_shot_prompt_builder(task_with_examples):
    # Verify the order of examples
    prompt_builder = MultiShotPromptBuilder(task=task_with_examples)
    prompt = prompt_builder.build_prompt()
    assert "Why did the cow cross the road?" in prompt
    assert prompt.index("Why did the cow cross the road?") < prompt.index(
        "Why don't cats play poker in the jungle?"
    )
    assert prompt.index("Why don't cats play poker in the jungle?") < prompt.index(
        "Why did the dog get a job?"
    )


# Add a new test for the FewShotPromptBuilder
def test_few_shot_prompt_builder(tmp_path):
    # Create a project and task hierarchy (similar to test_multi_shot_prompt_builder)
    project = Project(name="Test Project", path=(tmp_path / "test_project.kiln"))
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="You are an assistant which tells a joke, given a subject.",
        parent=project,
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                },
                "required": ["subject"],
            }
        ),
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"joke": {"type": "string"}},
                "required": ["joke"],
            }
        ),
    )
    task.save_to_file()

    # Create 6 examples (2 repaired, 4 high-quality)
    for i in range(6):
        run = TaskRun(
            input=f'{{"subject": "Subject {i+1}"}}',
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            parent=task,
            output=TaskOutput(
                output=f'{{"joke": "Joke Initial Output {i+1}"}}',
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
                rating=TaskOutputRating(value=4 + (i % 2), reason="Good joke"),
            ),
        )
        print("RATING", "Joke Initial Output ", i + 1, " - RATED:", 4 + (i % 2), "\n")
        if i < 2:
            run = run.model_copy(
                update={
                    "repair_instructions": "Fix the joke",
                    "repaired_output": TaskOutput(
                        output=f'{{"joke": "Repaired Joke {i+1}"}}',
                        source=DataSource(
                            type=DataSourceType.human,
                            properties={"created_by": "jane_doe"},
                        ),
                    ),
                }
            )
        run.save_to_file()

    # Check that only 4 examples are included
    prompt_builder = FewShotPromptBuilder(task=task)
    prompt = prompt_builder.build_prompt()
    assert prompt.count("## Example") == 4

    print("PROMPT", prompt)
    # Verify the order of examples (2 repaired, then 2 highest-rated)
    assert "Repaired Joke 1" in prompt
    assert "Repaired Joke 2" in prompt
    assert "Joke Initial Output 6" in prompt  # Rating 5
    assert "Joke Initial Output 4" in prompt  # Rating 5
    assert "Joke Initial Output 5" not in prompt  # Rating 4, not included
    assert "Joke Initial Output 3" not in prompt  # Rating 4, not included
    assert "Joke Initial Output 1" not in prompt  # Repaired, so using that
    assert "Joke Initial Output 2" not in prompt  # Repaired, so using that


def check_example_outputs(task: Task, count: int):
    prompt_builder = MultiShotPromptBuilder(task=task)
    prompt = prompt_builder.build_prompt()
    assert "# Instruction" in prompt
    assert task.instruction in prompt
    if count == 0:
        assert "# Example Outputs" not in prompt
    else:
        assert "# Example Outputs" in prompt
        assert f"## Example {count}" in prompt


def test_prompt_builder_name():
    assert SimplePromptBuilder.prompt_builder_name() == "simple_prompt_builder"
    assert MultiShotPromptBuilder.prompt_builder_name() == "multi_shot_prompt_builder"
    assert RepairsPromptBuilder.prompt_builder_name() == "repairs_prompt_builder"


def test_prompt_builder_from_ui_name():
    assert prompt_builder_from_ui_name("basic") == SimplePromptBuilder
    assert prompt_builder_from_ui_name("few_shot") == FewShotPromptBuilder
    assert prompt_builder_from_ui_name("many_shot") == MultiShotPromptBuilder
    assert prompt_builder_from_ui_name("repairs") == RepairsPromptBuilder

    with pytest.raises(ValueError, match="Unknown prompt builder: invalid_name"):
        prompt_builder_from_ui_name("invalid_name")


def test_example_count():
    assert FewShotPromptBuilder.example_count() == 4
    assert MultiShotPromptBuilder.example_count() == 25


def test_repair_multi_shot_prompt_builder(task_with_examples):
    # Verify the order of examples
    prompt_builder = RepairsPromptBuilder(task=task_with_examples)
    prompt = prompt_builder.build_prompt()
    assert (
        'Repaired Output Which is Sufficient: {"joke": "Why did the cow cross the road? To get to the udder side!"}'
        in prompt
    )
    assert "Instructions On How to Improve the Initial Output: Fix the joke" in prompt
    assert (
        'Initial Output Which Was Insufficient: {"joke": "Moo I am a cow joke."}'
        in prompt
    )
