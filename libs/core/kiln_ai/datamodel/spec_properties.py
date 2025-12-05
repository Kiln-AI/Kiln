from enum import Enum
from typing import Annotated, Any, Literal, TypeVar

from pydantic import AfterValidator
from typing_extensions import TypedDict

T = TypeVar("T")


class SpecType(str, Enum):
    """Defines the type of spec."""

    # Functionality
    behaviour = "behaviour"
    tone = "tone"
    formatting = "formatting"
    localization = "localization"

    # Task Performance
    appropriate_tool_use = "appropriate_tool_use"
    reference_answer_accuracy = "reference_answer_accuracy"

    # Accuracy
    factual_correctness = "factual_correctness"
    hallucinations = "hallucinations"
    completeness = "completeness"

    # Safety
    toxicity = "toxicity"
    bias = "bias"
    maliciousness = "maliciousness"
    nsfw = "nsfw"
    taboo = "taboo"

    # System Constraints
    jailbreak = "jailbreak"
    prompt_leakage = "prompt_leakage"


def validate_string_properties(
    properties: T,
    required_fields: list[str],
    optional_fields: list[str] | None = None,
) -> T:
    """
    Validates string properties in a TypedDict.

    Args:
        properties: The properties dictionary to validate
        required_fields: List of field names that must not be empty
        optional_fields: List of field names that must not be empty if provided

    Returns:
        The validated properties dictionary
    """
    props_dict: Any = properties
    for field in required_fields:
        value = props_dict.get(field)
        if value is None or not value.strip():
            raise ValueError(f"{field} cannot be empty")

    if optional_fields:
        for field in optional_fields:
            value = props_dict.get(field)
            if value is not None and not value.strip():
                raise ValueError(f"{field} if provided cannot be empty")

    return properties


class BehaviourProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.behaviour]
    base_instruction: str
    behavior_description: str
    correct_behavior_examples: str | None
    incorrect_behavior_examples: str | None


def validate_behaviour_properties(
    properties: BehaviourProperties,
) -> BehaviourProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "behavior_description"],
        optional_fields=["correct_behavior_examples", "incorrect_behavior_examples"],
    )


BehaviourPropertiesValidator = Annotated[
    BehaviourProperties,
    AfterValidator(lambda v: validate_behaviour_properties(v)),
]


class ToneProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.tone]
    base_instruction: str
    tone_description: str
    acceptable_examples: str | None
    unacceptable_examples: str | None


def validate_tone_properties(properties: ToneProperties) -> ToneProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "tone_description"],
        optional_fields=["acceptable_examples", "unacceptable_examples"],
    )


TonePropertiesValidator = Annotated[
    ToneProperties,
    AfterValidator(lambda v: validate_tone_properties(v)),
]


class FormattingProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.formatting]
    base_instruction: str
    formatting_requirements: str
    proper_formatting_examples: str | None
    improper_formatting_examples: str | None


def validate_formatting_properties(
    properties: FormattingProperties,
) -> FormattingProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "formatting_requirements"],
        optional_fields=["proper_formatting_examples", "improper_formatting_examples"],
    )


FormattingPropertiesValidator = Annotated[
    FormattingProperties,
    AfterValidator(lambda v: validate_formatting_properties(v)),
]


class LocalizationProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.localization]
    base_instruction: str
    localization_requirements: str
    violation_examples: str


def validate_localization_properties(
    properties: LocalizationProperties,
) -> LocalizationProperties:
    return validate_string_properties(
        properties,
        required_fields=[
            "base_instruction",
            "localization_requirements",
            "violation_examples",
        ],
    )


LocalizationPropertiesValidator = Annotated[
    LocalizationProperties,
    AfterValidator(lambda v: validate_localization_properties(v)),
]


class AppropriateToolUseProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.appropriate_tool_use]
    base_instruction: str
    tool_id: str
    tool_function_name: str
    tool_use_guidelines: str
    appropriate_tool_use_examples: str
    inappropriate_tool_use_examples: str


def validate_appropriate_tool_use_properties(
    properties: AppropriateToolUseProperties,
) -> AppropriateToolUseProperties:
    return validate_string_properties(
        properties,
        required_fields=[
            "base_instruction",
            "tool_id",
            "tool_function_name",
            "tool_use_guidelines",
            "appropriate_tool_use_examples",
            "inappropriate_tool_use_examples",
        ],
    )


AppropriateToolUsePropertiesValidator = Annotated[
    AppropriateToolUseProperties,
    AfterValidator(lambda v: validate_appropriate_tool_use_properties(v)),
]


class ReferenceAnswerAccuracyProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.reference_answer_accuracy]
    base_instruction: str
    reference_answer_accuracy_description: str
    accurate_examples: str
    inaccurate_examples: str


def validate_reference_answer_accuracy_properties(
    properties: ReferenceAnswerAccuracyProperties,
) -> ReferenceAnswerAccuracyProperties:
    return validate_string_properties(
        properties,
        required_fields=[
            "base_instruction",
            "reference_answer_accuracy_description",
            "accurate_examples",
            "inaccurate_examples",
        ],
    )


ReferenceAnswerAccuracyPropertiesValidator = Annotated[
    ReferenceAnswerAccuracyProperties,
    AfterValidator(lambda v: validate_reference_answer_accuracy_properties(v)),
]


class FactualCorrectnessProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.factual_correctness]
    base_instruction: str
    factually_inaccurate_examples: str


def validate_factual_correctness_properties(
    properties: FactualCorrectnessProperties,
) -> FactualCorrectnessProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "factually_inaccurate_examples"],
    )


FactualCorrectnessPropertiesValidator = Annotated[
    FactualCorrectnessProperties,
    AfterValidator(lambda v: validate_factual_correctness_properties(v)),
]


class HallucinationsProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.hallucinations]
    base_instruction: str
    hallucinations_examples: str


def validate_hallucinations_properties(
    properties: HallucinationsProperties,
) -> HallucinationsProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "hallucinations_examples"],
    )


HallucinationsPropertiesValidator = Annotated[
    HallucinationsProperties,
    AfterValidator(lambda v: validate_hallucinations_properties(v)),
]


class CompletenessProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.completeness]
    base_instruction: str
    complete_examples: str
    incomplete_examples: str


def validate_completeness_properties(
    properties: CompletenessProperties,
) -> CompletenessProperties:
    return validate_string_properties(
        properties,
        required_fields=[
            "base_instruction",
            "complete_examples",
            "incomplete_examples",
        ],
    )


CompletenessPropertiesValidator = Annotated[
    CompletenessProperties,
    AfterValidator(lambda v: validate_completeness_properties(v)),
]


class ToxicityProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.toxicity]
    base_instruction: str
    toxicity_examples: str


def validate_toxicity_properties(
    properties: ToxicityProperties,
) -> ToxicityProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "toxicity_examples"],
    )


ToxicityPropertiesValidator = Annotated[
    ToxicityProperties,
    AfterValidator(lambda v: validate_toxicity_properties(v)),
]


class BiasProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.bias]
    base_instruction: str
    bias_examples: str


def validate_bias_properties(properties: BiasProperties) -> BiasProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "bias_examples"],
    )


BiasPropertiesValidator = Annotated[
    BiasProperties,
    AfterValidator(lambda v: validate_bias_properties(v)),
]


class MaliciousnessProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.maliciousness]
    base_instruction: str
    malicious_examples: str


def validate_maliciousness_properties(
    properties: MaliciousnessProperties,
) -> MaliciousnessProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "malicious_examples"],
    )


MaliciousnessPropertiesValidator = Annotated[
    MaliciousnessProperties,
    AfterValidator(lambda v: validate_maliciousness_properties(v)),
]


class NsfwProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.nsfw]
    base_instruction: str
    nsfw_examples: str


def validate_nsfw_properties(properties: NsfwProperties) -> NsfwProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "nsfw_examples"],
    )


NsfwPropertiesValidator = Annotated[
    NsfwProperties,
    AfterValidator(lambda v: validate_nsfw_properties(v)),
]


class TabooProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.taboo]
    base_instruction: str
    taboo_examples: str


def validate_taboo_properties(properties: TabooProperties) -> TabooProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "taboo_examples"],
    )


TabooPropertiesValidator = Annotated[
    TabooProperties,
    AfterValidator(lambda v: validate_taboo_properties(v)),
]


class JailbreakProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.jailbreak]
    base_instruction: str
    jailbroken_examples: str


def validate_jailbreak_properties(
    properties: JailbreakProperties,
) -> JailbreakProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "jailbroken_examples"],
    )


JailbreakPropertiesValidator = Annotated[
    JailbreakProperties,
    AfterValidator(lambda v: validate_jailbreak_properties(v)),
]


class PromptLeakageProperties(TypedDict, total=True):
    spec_type: Literal[SpecType.prompt_leakage]
    base_instruction: str
    leakage_examples: str


def validate_prompt_leakage_properties(
    properties: PromptLeakageProperties,
) -> PromptLeakageProperties:
    return validate_string_properties(
        properties,
        required_fields=["base_instruction", "leakage_examples"],
    )


PromptLeakagePropertiesValidator = Annotated[
    PromptLeakageProperties,
    AfterValidator(lambda v: validate_prompt_leakage_properties(v)),
]


SpecProperties = (
    BehaviourPropertiesValidator
    | TonePropertiesValidator
    | FormattingPropertiesValidator
    | LocalizationPropertiesValidator
    | AppropriateToolUsePropertiesValidator
    | ReferenceAnswerAccuracyPropertiesValidator
    | FactualCorrectnessPropertiesValidator
    | HallucinationsPropertiesValidator
    | CompletenessPropertiesValidator
    | ToxicityPropertiesValidator
    | BiasPropertiesValidator
    | MaliciousnessPropertiesValidator
    | NsfwPropertiesValidator
    | TabooPropertiesValidator
    | JailbreakPropertiesValidator
    | PromptLeakagePropertiesValidator
)
