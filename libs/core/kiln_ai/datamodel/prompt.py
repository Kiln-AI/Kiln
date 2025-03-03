from pydantic import BaseModel, Field

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentedModel


class BasePrompt(BaseModel):
    """
    A prompt for a task. This is the basic data storage format which can be used throughout a project.

    The "Prompt" model name is reserved for the custom prompts parented by a task.
    """

    name: str = NAME_FIELD
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
    chain_of_thought_instructions: str | None = Field(
        default=None,
        description="Instructions for the model 'thinking' about the requirement prior to answering. Used for chain of thought style prompting. COT will not be used unless this is provided.",
    )


class Prompt(KilnParentedModel, BasePrompt):
    """
    A prompt for a task. This is the custom prompt parented by a task.
    """

    pass
