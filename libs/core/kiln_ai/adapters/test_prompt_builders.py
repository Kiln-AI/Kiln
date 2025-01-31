import json

import pytest

from kiln_ai.adapters.model_adapters.base_adapter import AdapterInfo, BaseAdapter
from kiln_ai.adapters.prompt_builders import (
    FewShotChainOfThoughtPromptBuilder,
    FewShotPromptBuilder,
    MultiShotChainOfThoughtPromptBuilder,
    MultiShotPromptBuilder,
    RepairsPromptBuilder,
    SavedPromptBuilder,
    SimpleChainOfThoughtPromptBuilder,
    SimplePromptBuilder,
    chain_of_thought_prompt,
    prompt_builder_from_ui_name,
)
from kiln_ai.adapters.test_prompt_adaptors import build_test_task
from kiln_ai.adapters.test_structured_output import build_structured_output_test_task
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Prompt,
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

    user_msg = builder.build_user_message(input)
    assert input in user_msg
    assert input not in prompt


def test_simple_prompt_builder_structured_input_non_ascii(tmp_path):
    task = build_structured_output_test_task(tmp_path)
    builder = SimplePromptBuilder(task=task)
    input = {"key": "你好👋"}
    user_msg = builder.build_user_message(input)
    assert "你好👋" in user_msg


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
            input=f'{{"subject": "Subject {i + 1}"}}',
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            parent=task,
            output=TaskOutput(
                output=f'{{"joke": "Joke Initial Output {i + 1}"}}',
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
                        output=f'{{"joke": "Repaired Joke {i + 1}"}}',
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


def test_prompt_builder_from_ui_name(task_with_examples):
    task = task_with_examples
    assert isinstance(prompt_builder_from_ui_name("basic", task), SimplePromptBuilder)
    assert isinstance(
        prompt_builder_from_ui_name("few_shot", task), FewShotPromptBuilder
    )
    assert isinstance(
        prompt_builder_from_ui_name("many_shot", task), MultiShotPromptBuilder
    )
    assert isinstance(
        prompt_builder_from_ui_name("repairs", task), RepairsPromptBuilder
    )
    assert isinstance(
        prompt_builder_from_ui_name("simple_chain_of_thought", task),
        SimpleChainOfThoughtPromptBuilder,
    )
    assert isinstance(
        prompt_builder_from_ui_name("few_shot_chain_of_thought", task),
        FewShotChainOfThoughtPromptBuilder,
    )
    assert isinstance(
        prompt_builder_from_ui_name("multi_shot_chain_of_thought", task),
        MultiShotChainOfThoughtPromptBuilder,
    )

    with pytest.raises(ValueError, match="Unknown prompt builder: invalid_name"):
        prompt_builder_from_ui_name("invalid_name", task)

    with pytest.raises(ValueError, match="Prompt ID not found: 123"):
        prompt_builder_from_ui_name("id::123", task)

    prompt = Prompt(
        name="test_prompt_name",
        prompt="test_prompt",
        chain_of_thought_instructions="coti",
        parent=task,
    )
    prompt.save_to_file()
    pb = prompt_builder_from_ui_name("id::" + prompt.id, task)
    assert isinstance(pb, SavedPromptBuilder)
    assert pb.prompt_id() == prompt.id
    assert pb.build_prompt() == "test_prompt"
    assert pb.chain_of_thought_prompt() == "coti"


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


def test_chain_of_thought_prompt(tmp_path):
    # Test with default thinking instruction
    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=None,
        thinking_instruction=None,
    )
    assert (
        chain_of_thought_prompt(task)
        == "Think step by step, explaining your reasoning."
    )

    # Test with custom thinking instruction
    custom_instruction = "First analyze the problem, then break it down into steps."
    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=None,
        thinking_instruction=custom_instruction,
    )
    assert chain_of_thought_prompt(task) == custom_instruction


@pytest.mark.parametrize(
    "builder_class",
    [
        SimpleChainOfThoughtPromptBuilder,
        FewShotChainOfThoughtPromptBuilder,
        MultiShotChainOfThoughtPromptBuilder,
    ],
)
def test_chain_of_thought_prompt_builders(builder_class, task_with_examples):
    # Test with default thinking instruction
    builder = builder_class(task=task_with_examples)
    assert (
        builder.chain_of_thought_prompt()
        == "Think step by step, explaining your reasoning."
    )

    # Test with custom thinking instruction
    custom_instruction = "First analyze the problem, then break it down into steps."
    task_with_custom = task_with_examples.model_copy(
        update={"thinking_instruction": custom_instruction}
    )
    builder = builder_class(task=task_with_custom)
    assert builder.chain_of_thought_prompt() == custom_instruction


def test_build_prompt_for_ui(tmp_path):
    # Test regular prompt builder
    task = build_test_task(tmp_path)
    simple_builder = SimplePromptBuilder(task=task)
    ui_prompt = simple_builder.build_prompt_for_ui()

    # Should match regular prompt since no chain of thought
    assert ui_prompt == simple_builder.build_prompt()
    assert "# Thinking Instructions" not in ui_prompt

    # Test chain of thought prompt builder
    cot_builder = SimpleChainOfThoughtPromptBuilder(task=task)
    ui_prompt_cot = cot_builder.build_prompt_for_ui()

    # Should include both base prompt and thinking instructions
    assert cot_builder.build_prompt() in ui_prompt_cot
    assert "# Thinking Instructions" in ui_prompt_cot
    assert "Think step by step" in ui_prompt_cot

    # Test with custom thinking instruction
    custom_instruction = "First analyze the problem, then solve it."
    task_with_custom = task.model_copy(
        update={"thinking_instruction": custom_instruction}
    )
    custom_cot_builder = SimpleChainOfThoughtPromptBuilder(task=task_with_custom)
    ui_prompt_custom = custom_cot_builder.build_prompt_for_ui()

    assert custom_cot_builder.build_prompt() in ui_prompt_custom
    assert "# Thinking Instructions" in ui_prompt_custom
    assert custom_instruction in ui_prompt_custom


def test_saved_prompt_builder(tmp_path):
    task = build_test_task(tmp_path)

    prompt = Prompt(
        name="test_prompt_name",
        prompt="test_prompt",
        parent=task,
    )
    prompt.save_to_file()

    builder = SavedPromptBuilder(task=task, prompt_id=prompt.id)
    assert builder.build_prompt() == "test_prompt"
    assert builder.chain_of_thought_prompt() is None
    assert builder.build_prompt_for_ui() == "test_prompt"
    assert builder.prompt_id() == prompt.id


def test_saved_prompt_builder_with_chain_of_thought(tmp_path):
    task = build_test_task(tmp_path)

    prompt = Prompt(
        name="test_prompt_name",
        prompt="test_prompt",
        chain_of_thought_instructions="Think step by step",
        parent=task,
    )
    prompt.save_to_file()

    builder = SavedPromptBuilder(task=task, prompt_id=prompt.id)
    assert builder.build_prompt() == "test_prompt"
    assert builder.chain_of_thought_prompt() == "Think step by step"
    assert "Think step by step" in builder.build_prompt_for_ui()
    assert builder.prompt_id() == prompt.id


def test_saved_prompt_builder_not_found(tmp_path):
    task = build_test_task(tmp_path)

    with pytest.raises(ValueError, match="Prompt ID not found: 123"):
        SavedPromptBuilder(task=task, prompt_id="123")
