from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator
from typing_extensions import TypedDict


class SpecType(str, Enum):
    """Defines the type of spec."""

    # Functionality
    desired_behaviour = "desired_behaviour"
    undesired_behaviour = "undesired_behaviour"

    # Reasoning & Execution
    appropriate_tool_use = "appropriate_tool_use"
    intermediate_reasoning = "intermediate_reasoning"

    # Correctness
    reference_answer_accuracy = "reference_answer_accuracy"
    factual_correctness = "factual_correctness"
    hallucinations = "hallucinations"
    completeness = "completeness"
    consistency = "consistency"

    # Style
    tone = "tone"
    formatting = "formatting"
    localization = "localization"

    # Safety
    toxicity = "toxicity"
    bias = "bias"
    maliciousness = "maliciousness"
    nsfw = "nsfw"
    taboo = "taboo"

    # System Constraints
    jailbreak = "jailbreak"
    prompt_leakage = "prompt_leakage"


class DesiredBehaviourProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.desired_behaviour]


class IntermediateReasoningProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.intermediate_reasoning]


class ReferenceAnswerAccuracyProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.reference_answer_accuracy]


class FactualCorrectnessProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.factual_correctness]


class HallucinationsProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.hallucinations]


class CompletenessProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.completeness]


class ConsistencyProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.consistency]


class ToneProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.tone]


class FormattingProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.formatting]


class LocalizationProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.localization]


class ToxicityProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.toxicity]


class BiasProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.bias]


class MaliciousnessProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.maliciousness]


class NsfwProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.nsfw]


class TabooProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.taboo]


class JailbreakProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.jailbreak]


class PromptLeakageProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.prompt_leakage]


class AppropriateToolUseProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.appropriate_tool_use]
    tool_id: str
    appropriate_tool_use_guidelines: str
    inappropriate_tool_use_guidelines: str | None


def validate_appropriate_tool_use_properties(
    properties: AppropriateToolUseProperties,
) -> AppropriateToolUseProperties:
    # tool_id
    tool_id = properties["tool_id"]
    if not tool_id.strip():
        raise ValueError("tool_id cannot be empty")

    # appropriate_tool_use_guidelines
    appropriate_tool_use_guidelines = properties["appropriate_tool_use_guidelines"]
    if not appropriate_tool_use_guidelines.strip():
        raise ValueError("appropriate_tool_use_guidelines cannot be empty")

    # inappropriate_tool_use_guidelines
    inappropriate_tool_use_guidelines = properties["inappropriate_tool_use_guidelines"]
    if (
        inappropriate_tool_use_guidelines is not None
        and not inappropriate_tool_use_guidelines.strip()
    ):
        raise ValueError(
            "inappropriate_tool_use_guidelines if provided cannot be empty"
        )

    return properties


class UndesiredBehaviourProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.undesired_behaviour]
    undesired_behaviour_guidelines: str
    examples: str


def validate_undesired_behaviour_properties(
    properties: UndesiredBehaviourProperties,
) -> UndesiredBehaviourProperties:
    # undesired_behaviour_guidelines
    undesired_behaviour_guidelines = properties["undesired_behaviour_guidelines"]
    if not undesired_behaviour_guidelines.strip():
        raise ValueError("undesired_behaviour_guidelines cannot be empty")

    # examples
    examples = properties["examples"]
    if not examples.strip():
        raise ValueError("examples cannot be empty")

    return properties


AppropriateToolUsePropertiesValidator = Annotated[
    AppropriateToolUseProperties,
    AfterValidator(lambda v: validate_appropriate_tool_use_properties(v)),
]

UndesiredBehaviourPropertiesValidator = Annotated[
    UndesiredBehaviourProperties,
    AfterValidator(lambda v: validate_undesired_behaviour_properties(v)),
]

SpecProperties = (
    DesiredBehaviourProperties
    | UndesiredBehaviourPropertiesValidator
    | AppropriateToolUsePropertiesValidator
    | IntermediateReasoningProperties
    | ReferenceAnswerAccuracyProperties
    | FactualCorrectnessProperties
    | HallucinationsProperties
    | CompletenessProperties
    | ConsistencyProperties
    | ToneProperties
    | FormattingProperties
    | LocalizationProperties
    | ToxicityProperties
    | BiasProperties
    | MaliciousnessProperties
    | NsfwProperties
    | TabooProperties
    | JailbreakProperties
    | PromptLeakageProperties
)
