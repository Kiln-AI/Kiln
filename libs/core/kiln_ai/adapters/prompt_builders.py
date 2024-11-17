import json
from abc import ABCMeta, abstractmethod
from typing import Dict

from kiln_ai.datamodel import RunnableTask, Task, TaskRun
from kiln_ai.utils.formatting import snake_case


class BasePromptBuilder(metaclass=ABCMeta):
    """Base class for building prompts from tasks.

    Provides the core interface and basic functionality for prompt builders.
    """

    def __init__(self, task: RunnableTask | Task):
        """Initialize the prompt builder with a task.

        Args:
            task (Task): The task containing instructions and requirements.
        """
        self.task = task

    @abstractmethod
    def build_prompt(self) -> str:
        """Build and return the complete prompt string.

        Returns:
            str: The constructed prompt.
        """
        pass

    @classmethod
    def prompt_builder_name(cls) -> str:
        """Returns the name of the prompt builder, to be used for persisting into the datastore.

        Default implementation gets the name of the prompt builder in snake case. If you change the class name, you should override this so prior saved data is compatible.

        Returns:
            str: The prompt builder name in snake_case format.
        """
        return snake_case(cls.__name__)

    def build_user_message(self, input: Dict | str) -> str:
        """Build a user message from the input.

        Args:
            input (Union[Dict, str]): The input to format into a message.

        Returns:
            str: The formatted user message.
        """
        if isinstance(input, Dict):
            return f"The input is:\n{json.dumps(input, indent=2)}"

        return f"The input is:\n{input}"

    def chain_of_thought_prompt(self) -> str | None:
        """Build and return the chain of thought prompt string.

        Returns:
            str: The constructed chain of thought prompt.
        """
        return None

    def build_prompt_for_ui(self) -> str:
        """Build a prompt for the UI. It includes additional instructions (like chain of thought), even if they are passed to the model in stages.

        Designed for end-user consumption, not for model consumption.

        Returns:
            str: The constructed prompt string.
        """
        base_prompt = self.build_prompt()
        cot_prompt = self.chain_of_thought_prompt()
        if cot_prompt:
            base_prompt += "\n# Thinking Instructions\n\n" + cot_prompt
        return base_prompt


class SimplePromptBuilder(BasePromptBuilder):
    """A basic prompt builder that combines task instruction with requirements."""

    def build_prompt(self) -> str:
        """Build a simple prompt with instruction and requirements.

        Returns:
            str: The constructed prompt string.
        """
        base_prompt = self.task.instruction

        # TODO: this is just a quick version. Formatting and best practices TBD
        if len(self.task.requirements) > 0:
            base_prompt += (
                "\n\nYour response should respect the following requirements:\n"
            )
            # iterate requirements, formatting them in numbereed list like 1) task.instruction\n2)...
            for i, requirement in enumerate(self.task.requirements):
                base_prompt += f"{i+1}) {requirement.instruction}\n"

        return base_prompt


class MultiShotPromptBuilder(BasePromptBuilder):
    """A prompt builder that includes multiple examples in the prompt."""

    @classmethod
    def example_count(cls) -> int:
        """Get the maximum number of examples to include in the prompt.

        Returns:
            int: The maximum number of examples (default 25).
        """
        return 25

    def build_prompt(self) -> str:
        """Build a prompt with instruction, requirements, and multiple examples.

        Returns:
            str: The constructed prompt string with examples.
        """
        base_prompt = f"# Instruction\n\n{ self.task.instruction }\n\n"

        if len(self.task.requirements) > 0:
            base_prompt += "# Requirements\n\nYour response should respect the following requirements:\n"
            for i, requirement in enumerate(self.task.requirements):
                base_prompt += f"{i+1}) {requirement.instruction}\n"
            base_prompt += "\n"

        valid_examples = self.collect_examples()

        if len(valid_examples) == 0:
            return base_prompt

        base_prompt += "# Example Outputs\n\n"
        for i, example in enumerate(valid_examples):
            base_prompt += self.prompt_section_for_example(i, example)

        return base_prompt

    def prompt_section_for_example(self, index: int, example: TaskRun) -> str:
        # Prefer repaired output if it exists, otherwise use the regular output
        output = example.repaired_output or example.output
        return f"## Example {index+1}\n\nInput: {example.input}\nOutput: {output.output}\n\n"

    def collect_examples(self) -> list[TaskRun]:
        if not isinstance(self.task, Task):
            raise ValueError(
                "Can't generate a multi-shot prompt without a persisted task"
            )

        valid_examples: list[TaskRun] = []
        runs = self.task.runs()

        # first pass, we look for repaired outputs. These are the best examples.
        for run in runs:
            if len(valid_examples) >= self.__class__.example_count():
                break
            if run.repaired_output is not None:
                valid_examples.append(run)

        # second pass, we look for high quality outputs (rating based)
        # Minimum is "high_quality" (4 star in star rating scale), then sort by rating
        # exclude repaired outputs as they were used above
        runs_with_rating = [
            run
            for run in runs
            if run.output.rating is not None
            and run.output.rating.value is not None
            and run.output.rating.is_high_quality()
            and run.repaired_output is None
        ]
        runs_with_rating.sort(
            key=lambda x: (x.output.rating and x.output.rating.value) or 0, reverse=True
        )
        for run in runs_with_rating:
            if len(valid_examples) >= self.__class__.example_count():
                break
            valid_examples.append(run)
        return valid_examples


class FewShotPromptBuilder(MultiShotPromptBuilder):
    """A prompt builder that includes a small number of examples in the prompt."""

    @classmethod
    def example_count(cls) -> int:
        """Get the maximum number of examples to include in the prompt.

        Returns:
            int: The maximum number of examples (4).
        """
        return 4


class RepairsPromptBuilder(MultiShotPromptBuilder):
    """A prompt builder that includes multiple examples in the prompt, including repaired instructions describing what was wrong, and how it was fixed."""

    def prompt_section_for_example(self, index: int, example: TaskRun) -> str:
        if (
            not example.repaired_output
            or not example.repair_instructions
            or not example.repaired_output.output
        ):
            return super().prompt_section_for_example(index, example)

        prompt_section = f"## Example {index+1}\n\nInput: {example.input}\n\n"
        prompt_section += (
            f"Initial Output Which Was Insufficient: {example.output.output}\n\n"
        )
        prompt_section += f"Instructions On How to Improve the Initial Output: {example.repair_instructions}\n\n"
        prompt_section += (
            f"Repaired Output Which is Sufficient: {example.repaired_output.output}\n\n"
        )
        return prompt_section


def chain_of_thought_prompt(task: RunnableTask) -> str | None:
    """Standard implementation to build and return the chain of thought prompt string.

    Returns:
        str: The constructed chain of thought prompt.
    """

    cot_instruction = task.thinking_instruction
    if not cot_instruction:
        cot_instruction = "Think step by step, explaining your reasoning."

    return cot_instruction


class SimpleChainOfThoughtPromptBuilder(SimplePromptBuilder):
    """A prompt builder that includes a chain of thought prompt on top of the simple prompt."""

    def chain_of_thought_prompt(self) -> str | None:
        return chain_of_thought_prompt(self.task)


class FewShotChainOfThoughtPromptBuilder(FewShotPromptBuilder):
    """A prompt builder that includes a chain of thought prompt on top of the few shot prompt."""

    def chain_of_thought_prompt(self) -> str | None:
        return chain_of_thought_prompt(self.task)


class MultiShotChainOfThoughtPromptBuilder(MultiShotPromptBuilder):
    """A prompt builder that includes a chain of thought prompt on top of the multi shot prompt."""

    def chain_of_thought_prompt(self) -> str | None:
        return chain_of_thought_prompt(self.task)


prompt_builder_registry = {
    "simple_prompt_builder": SimplePromptBuilder,
    "multi_shot_prompt_builder": MultiShotPromptBuilder,
    "few_shot_prompt_builder": FewShotPromptBuilder,
    "repairs_prompt_builder": RepairsPromptBuilder,
    "simple_chain_of_thought_prompt_builder": SimpleChainOfThoughtPromptBuilder,
    "few_shot_chain_of_thought_prompt_builder": FewShotChainOfThoughtPromptBuilder,
    "multi_shot_chain_of_thought_prompt_builder": MultiShotChainOfThoughtPromptBuilder,
}


# Our UI has some names that are not the same as the class names, which also hint parameters.
def prompt_builder_from_ui_name(ui_name: str) -> type[BasePromptBuilder]:
    """Convert a name used in the UI to the corresponding prompt builder class.

    Args:
        ui_name (str): The UI name for the prompt builder type.

    Returns:
        type[BasePromptBuilder]: The corresponding prompt builder class.

    Raises:
        ValueError: If the UI name is not recognized.
    """
    match ui_name:
        case "basic":
            return SimplePromptBuilder
        case "few_shot":
            return FewShotPromptBuilder
        case "many_shot":
            return MultiShotPromptBuilder
        case "repairs":
            return RepairsPromptBuilder
        case "simple_chain_of_thought":
            return SimpleChainOfThoughtPromptBuilder
        case "few_shot_chain_of_thought":
            return FewShotChainOfThoughtPromptBuilder
        case "multi_shot_chain_of_thought":
            return MultiShotChainOfThoughtPromptBuilder
        case _:
            raise ValueError(f"Unknown prompt builder: {ui_name}")
