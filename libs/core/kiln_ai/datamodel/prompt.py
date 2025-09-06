from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel


class ThinkingStrategyType(str, Enum):
    """Type of thinking strategy to use."""

    chain_of_thought = "chain_of_thought"
    react = "react"


class BaseThinkingStrategy(BaseModel):
    """Base class for thinking strategies."""

    type: ThinkingStrategyType


class ChainOfThoughtThinkingStrategy(BaseThinkingStrategy):
    """Chain of thought strategy with custom instructions."""

    type: Literal[ThinkingStrategyType.chain_of_thought] = (
        ThinkingStrategyType.chain_of_thought
    )
    instructions: str = Field(
        default="Think step by step, explaining your reasoning.",
        description="Instructions for how the model should think through the problem.",
    )


class ReActThinkingStrategy(BaseThinkingStrategy):
    """ReAct (Reasoning + Acting) strategy."""

    type: Literal[ThinkingStrategyType.react] = ThinkingStrategyType.react
    instructions: str = Field(
        default="Think step by step. For each step, first think about what to do, then determine what action to take, if any.",
        description="Instructions for how the model should think through using tools for the problem.",
    )


# Union type for all thinking strategies
ThinkingStrategy = Union[
    ChainOfThoughtThinkingStrategy,
    ReActThinkingStrategy,
    None,
]


class BasePrompt(BaseModel):
    """
    A prompt for a task. This is the basic data storage format which can be used throughout a project.

    The "Prompt" model name is reserved for the custom prompts parented by a task.
    """

    name: FilenameString = Field(description="The name of the prompt.")
    description: str | None = Field(
        default=None,
        description="A more detailed description of the prompt.",
    )
    generator_id: str | None = Field(
        default=None,
        description="The id of the generator that created this prompt.",
    )
    prompt: str = Field(
        description="The prompt for the task.",
        min_length=1,
    )
    thinkingStrategy: ThinkingStrategy = Field(
        default=None,
        description="Strategy for how the model should think about the problem before responding.",
    )

    @model_validator(mode="before")
    @classmethod
    def upgrade_chain_of_thought_instructions(cls, data):
        """Upgrade old chain_of_thought_instructions to new thinkingStrategy format."""
        if isinstance(data, dict) and "chain_of_thought_instructions" in data:
            cot_instructions = data.pop("chain_of_thought_instructions")

            # If chain_of_thought_instructions was provided, create a ChainOfThoughtThinkingStrategy
            if cot_instructions:
                data["thinkingStrategy"] = {
                    "type": "chain_of_thought",
                    "instructions": cot_instructions,
                }
            # If it was None, don't set thinkingStrategy (it will default to None)

        return data

    def get_thinking_instructions(self) -> str | None:
        """Get thinking instructions for backward compatibility."""
        if isinstance(self.thinkingStrategy, ChainOfThoughtThinkingStrategy):
            return self.thinkingStrategy.instructions
        elif isinstance(self.thinkingStrategy, ReActThinkingStrategy):
            return self.thinkingStrategy.instructions
        else:
            return None

    def has_thinking_strategy(self) -> bool:
        """Check if this prompt uses any thinking strategy."""
        return self.thinkingStrategy is not None


class Prompt(KilnParentedModel, BasePrompt):
    """
    A prompt for a task. This is the custom prompt parented by a task.
    """

    pass
