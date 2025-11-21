from typing import Literal, TypedDict


class AppropriateToolUseProperties(TypedDict, total=True):
    spec_type: Literal["appropriate_tool_use"]
    tool_id: str
    appropriate_tool_use_guidelines: str
    inappropriate_tool_use_guidelines: str | None


class UndesiredBehaviourProperties(TypedDict, total=True):
    spec_type: Literal["undesired_behaviour"]
    undesired_behaviour_guidelines: str
    examples: str


SpecProperties = AppropriateToolUseProperties | UndesiredBehaviourProperties
