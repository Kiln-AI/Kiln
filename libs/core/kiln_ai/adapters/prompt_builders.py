import json
from abc import ABCMeta, abstractmethod
from typing import Dict, Union

from kiln_ai.datamodel import Task
from kiln_ai.utils.formatting import snake_case


class BasePromptBuilder(metaclass=ABCMeta):
    """Base class for building prompts from tasks.

    Provides the core interface and basic functionality for prompt builders.
    """

    def __init__(self, task: Task):
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

        valid_examples: list[tuple[str, str]] = []
        runs = self.task.runs()

        # first pass, we look for repaired outputs. These are the best examples.
        for run in runs:
            if len(valid_examples) >= self.__class__.example_count():
                break
            if run.repaired_output is not None:
                valid_examples.append((run.input, run.repaired_output.output))

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
            valid_examples.append((run.input, run.output.output))

        if len(valid_examples) > 0:
            base_prompt += "# Example Outputs\n\n"
            for i, example in enumerate(valid_examples):
                base_prompt += (
                    f"## Example {i+1}\n\nInput: {example[0]}\nOutput: {example[1]}\n\n"
                )

        return base_prompt


class FewShotPromptBuilder(MultiShotPromptBuilder):
    """A prompt builder that includes a small number of examples in the prompt."""

    @classmethod
    def example_count(cls) -> int:
        """Get the maximum number of examples to include in the prompt.

        Returns:
            int: The maximum number of examples (4).
        """
        return 4


prompt_builder_registry = {
    "simple_prompt_builder": SimplePromptBuilder,
    "multi_shot_prompt_builder": MultiShotPromptBuilder,
    "few_shot_prompt_builder": FewShotPromptBuilder,
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
        case _:
            raise ValueError(f"Unknown prompt builder: {ui_name}")
