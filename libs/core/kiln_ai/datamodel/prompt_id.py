from enum import Enum
from typing import Annotated

from pydantic import AfterValidator


# Generators that can take any task and build a prompt
class PromptGenerators(str, Enum):
    SIMPLE = "simple_prompt_builder"
    MULTI_SHOT = "multi_shot_prompt_builder"
    FEW_SHOT = "few_shot_prompt_builder"
    REPAIRS = "repairs_prompt_builder"
    SIMPLE_CHAIN_OF_THOUGHT = "simple_chain_of_thought_prompt_builder"
    FEW_SHOT_CHAIN_OF_THOUGHT = "few_shot_chain_of_thought_prompt_builder"
    MULTI_SHOT_CHAIN_OF_THOUGHT = "multi_shot_chain_of_thought_prompt_builder"


prompt_generator_values = [pg.value for pg in PromptGenerators]


PromptId = Annotated[
    str,
    AfterValidator(lambda v: _check_prompt_id(v)),
]
"""
A pydantic type that validates strings containing a valid prompt ID.

Prompt IDs can be one of:
- A saved prompt ID
- A fine-tune prompt ID
- A task run config ID
- A prompt generator name
"""


def _check_prompt_id(id: str) -> str:
    """
    Check that the prompt ID is valid.
    """
    if id in prompt_generator_values:
        return id

    if id.startswith("id::"):
        # check it has 4 parts divided by :: -- 'id::project_id::task_id::prompt_id'
        parts = id.split("::")
        if len(parts) != 2 or len(parts[1]) == 0:
            raise ValueError(
                f"Invalid saved prompt ID: {id}. Expected format: 'id::[prompt_id]'."
            )
        return id

    if id.startswith("task_run_config::"):
        # check it had a eval_id after the :: -- 'project_id::task_id::task_run_config_id'
        parts = id.split("::")
        if len(parts) != 4:
            raise ValueError(
                f"Invalid task run config prompt ID: {id}. Expected format: 'task_run_config::[project_id]::[task_id]::[task_run_config_id]'."
            )
        return id

    if id.startswith("fine_tune_prompt::"):
        # check it had a fine_tune_id after the :: -- 'fine_tune_prompt::fine_tune_id'
        fine_tune_id = id[18:]
        if len(fine_tune_id) == 0:
            raise ValueError(
                f"Invalid fine-tune prompt ID: {id}. Expected format: 'fine_tune_prompt::[fine_tune_id]'."
            )
        return id

    raise ValueError(f"Invalid prompt ID: {id}")


def is_frozen_prompt(id: PromptId) -> bool:
    """
    Check if the prompt ID is a frozen prompt.
    """
    if id.startswith("id::"):
        return True
    if id.startswith("task_run_config::"):
        return True
    if id.startswith("fine_tune_prompt::"):
        return True
    return False
