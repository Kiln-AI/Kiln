import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.spec import Spec, SpecStatus
from kiln_ai.datamodel.spec_properties import (
    AppropriateToolUseProperties,
    BiasProperties,
    CompletenessProperties,
    DesiredBehaviourProperties,
    FactualCorrectnessProperties,
    FormattingProperties,
    HallucinationsProperties,
    IssueProperties,
    JailbreakProperties,
    LocalizationProperties,
    MaliciousnessProperties,
    NsfwProperties,
    PromptLeakageProperties,
    ReferenceAnswerAccuracyProperties,
    SpecType,
    TabooProperties,
    ToneProperties,
    ToxicityProperties,
)
from kiln_ai.datamodel.task import Task


@pytest.fixture
def sample_task():
    return Task(name="Test Task", instruction="Test instruction")


@pytest.fixture
def sample_tone_properties():
    return ToneProperties(
        spec_type=SpecType.tone,
        base_instruction="Test instruction",
        tone_description="Professional and friendly",
    )


def test_spec_valid_creation(sample_task):
    """Test creating a spec with all required fields."""
    properties = ToneProperties(
        spec_type=SpecType.tone,
        base_instruction="Test instruction",
        tone_description="Professional and friendly",
    )
    spec = Spec(
        name="Test Spec",
        definition="The system should behave correctly",
        properties=properties,
        parent=sample_task,
    )

    assert spec.name == "Test Spec"
    assert spec.definition == "The system should behave correctly"
    assert spec.properties["spec_type"] == SpecType.tone
    assert spec.priority == Priority.p1
    assert spec.status == SpecStatus.active
    assert spec.tags == []
    assert spec.eval_id is None


def test_spec_with_custom_values(sample_task):
    """Test creating a spec with custom priority, status, and tags."""
    properties = ToxicityProperties(
        spec_type=SpecType.toxicity,
        base_instruction="Test instruction",
        toxicity_examples="Example: offensive language",
    )
    spec = Spec(
        name="Custom Spec",
        definition="No toxic content should be present",
        properties=properties,
        priority=Priority.p2,
        status=SpecStatus.active,
        tags=["tag1", "tag2"],
        eval_id="test_eval_id",
        parent=sample_task,
    )

    assert spec.priority == Priority.p2
    assert spec.status == SpecStatus.active
    assert spec.tags == ["tag1", "tag2"]
    assert spec.eval_id == "test_eval_id"


def test_spec_missing_required_fields(sample_task, sample_tone_properties):
    """Test that spec creation fails without required fields."""
    # Missing name
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            definition="Test definition",
            properties=sample_tone_properties,
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing definition
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            properties=sample_tone_properties,
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing properties
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            definition="Test definition",
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)


def test_spec_empty_name(sample_task, sample_tone_properties):
    """Test that spec creation fails with empty name."""
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="",
            definition="Test definition",
            properties=sample_tone_properties,
            parent=sample_task,
        )
    assert "Name is too short" in str(exc_info.value)


def test_spec_empty_definition(sample_task, sample_tone_properties):
    """Test that spec creation fails with empty definition."""
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            definition="",
            properties=sample_tone_properties,
            parent=sample_task,
        )
    assert "String should have at least 1 character" in str(exc_info.value)


def create_sample_properties(spec_type: SpecType):
    """Helper to create sample properties for testing."""
    base_instruction = "Test instruction"

    if spec_type == SpecType.desired_behaviour:
        return DesiredBehaviourProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            desired_behaviour_description="Test desired behaviour",
        )
    elif spec_type == SpecType.issue:
        return IssueProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            issue_description="Test issue description",
        )
    elif spec_type == SpecType.tone:
        return ToneProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            tone_description="Professional",
        )
    elif spec_type == SpecType.formatting:
        return FormattingProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            formatting_requirements="Use markdown",
        )
    elif spec_type == SpecType.localization:
        return LocalizationProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            localization_requirements="Support en-US",
            violation_examples="Example: using wrong language",
        )
    elif spec_type == SpecType.appropriate_tool_use:
        return AppropriateToolUseProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            tool_id="test_tool_id",
            tool_function_name="test_tool",
            tool_use_guidelines="Use when needed",
            appropriate_tool_use_examples="Example: correct tool usage",
            inappropriate_tool_use_examples="Example: incorrect tool usage",
        )
    elif spec_type == SpecType.reference_answer_accuracy:
        return ReferenceAnswerAccuracyProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            reference_answer_accuracy_description="Must match reference",
            accurate_examples="Example: accurate answer",
            inaccurate_examples="Example: inaccurate answer",
        )
    elif spec_type == SpecType.factual_correctness:
        return FactualCorrectnessProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            factually_inaccurate_examples="Example: wrong date",
        )
    elif spec_type == SpecType.hallucinations:
        return HallucinationsProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            hallucinations_examples="Example: made up fact",
        )
    elif spec_type == SpecType.completeness:
        return CompletenessProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            complete_examples="Example: complete answer",
            incomplete_examples="Example: incomplete answer",
        )
    elif spec_type == SpecType.toxicity:
        return ToxicityProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            toxicity_examples="Example: offensive language",
        )
    elif spec_type == SpecType.bias:
        return BiasProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            bias_examples="Example: biased statement",
        )
    elif spec_type == SpecType.maliciousness:
        return MaliciousnessProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            malicious_examples="Example: harmful advice",
        )
    elif spec_type == SpecType.nsfw:
        return NsfwProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            nsfw_examples="Example: inappropriate content",
        )
    elif spec_type == SpecType.taboo:
        return TabooProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            taboo_examples="Example: taboo content",
        )
    elif spec_type == SpecType.jailbreak:
        return JailbreakProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            jailbroken_examples="Example: bypassing safety",
        )
    elif spec_type == SpecType.prompt_leakage:
        return PromptLeakageProperties(
            spec_type=spec_type,
            base_instruction=base_instruction,
            leakage_examples="Example: revealing system prompt",
        )
    else:
        raise ValueError(f"Unknown spec type: {spec_type}")


@pytest.mark.parametrize(
    "spec_type",
    [
        SpecType.desired_behaviour,
        SpecType.issue,
        SpecType.tone,
        SpecType.formatting,
        SpecType.localization,
        SpecType.appropriate_tool_use,
        SpecType.reference_answer_accuracy,
        SpecType.factual_correctness,
        SpecType.hallucinations,
        SpecType.completeness,
        SpecType.toxicity,
        SpecType.bias,
        SpecType.maliciousness,
        SpecType.nsfw,
        SpecType.taboo,
        SpecType.jailbreak,
        SpecType.prompt_leakage,
    ],
)
def test_spec_all_types(sample_task, spec_type):
    """Test that all spec types can be created."""
    properties = create_sample_properties(spec_type)
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=properties,
        parent=sample_task,
    )
    assert spec.properties["spec_type"] == spec_type


@pytest.mark.parametrize(
    "priority",
    [Priority.p0, Priority.p1, Priority.p2, Priority.p3],
)
def test_spec_all_priorities(sample_task, sample_tone_properties, priority):
    """Test that all priority levels can be set."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        priority=priority,
        parent=sample_task,
    )
    assert spec.priority == priority


@pytest.mark.parametrize(
    "status",
    [
        SpecStatus.active,
        SpecStatus.future,
        SpecStatus.deprecated,
        SpecStatus.archived,
    ],
)
def test_spec_all_statuses(sample_task, sample_tone_properties, status):
    """Test that all status values can be set."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        status=status,
        parent=sample_task,
    )
    assert spec.status == status


def test_spec_tags_validation_empty_string(sample_task, sample_tone_properties):
    """Test that tags cannot be empty strings."""
    with pytest.raises(ValidationError, match="tags cannot be empty strings"):
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=sample_tone_properties,
            tags=["valid_tag", ""],
            parent=sample_task,
        )


def test_spec_tags_validation_spaces(sample_task, sample_tone_properties):
    """Test that tags cannot contain spaces."""
    with pytest.raises(
        ValidationError, match=r"tags cannot contain spaces\. Try underscores\."
    ):
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=sample_tone_properties,
            tags=["valid_tag", "invalid tag"],
            parent=sample_task,
        )


def test_spec_tags_valid(sample_task, sample_tone_properties):
    """Test that valid tags work correctly."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        tags=["tag1", "tag_2", "tag-3", "TAG4"],
        parent=sample_task,
    )
    assert spec.tags == ["tag1", "tag_2", "tag-3", "TAG4"]


def test_spec_archived_status(sample_task, sample_tone_properties):
    """Test that archived status works correctly."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        status=SpecStatus.archived,
        parent=sample_task,
    )
    assert spec.status == SpecStatus.archived

    spec2 = Spec(
        name="Test Spec 2",
        definition="Test definition",
        properties=sample_tone_properties,
        status=SpecStatus.active,
        parent=sample_task,
    )
    assert spec2.status == SpecStatus.active


def test_spec_with_appropriate_tool_use_properties(sample_task):
    """Test creating a spec with AppropriateToolUseProperties."""
    properties = AppropriateToolUseProperties(
        spec_type=SpecType.appropriate_tool_use,
        base_instruction="Test instruction",
        tool_id="tool_123",
        tool_function_name="tool_function_123",
        tool_use_guidelines="Use the tool when needed",
        appropriate_tool_use_examples="Example: search queries",
        inappropriate_tool_use_examples="Example: simple math",
    )
    spec = Spec(
        name="Tool Use Spec",
        definition="Test tool use spec",
        properties=properties,
        parent=sample_task,
    )

    assert spec.properties is not None
    assert isinstance(spec.properties, dict)
    assert spec.properties["spec_type"] == SpecType.appropriate_tool_use
    assert spec.properties["tool_function_name"] == "tool_function_123"
    assert spec.properties["tool_use_guidelines"] == "Use the tool when needed"
    assert spec.properties["appropriate_tool_use_examples"] == "Example: search queries"
    assert spec.properties["inappropriate_tool_use_examples"] == "Example: simple math"


def test_spec_with_appropriate_tool_use_properties_all_fields(sample_task):
    """Test creating a spec with AppropriateToolUseProperties with all fields."""
    properties = AppropriateToolUseProperties(
        spec_type=SpecType.appropriate_tool_use,
        base_instruction="Test instruction",
        tool_id="tool_456",
        tool_function_name="tool_function_456",
        tool_use_guidelines="Use the tool when needed",
        appropriate_tool_use_examples="Example: correct usage",
        inappropriate_tool_use_examples="Example: incorrect usage",
    )
    spec = Spec(
        name="Tool Use Spec",
        definition="Test tool use spec",
        properties=properties,
        parent=sample_task,
    )

    assert spec.properties is not None
    assert isinstance(spec.properties, dict)
    assert (
        spec.properties.get("appropriate_tool_use_examples") == "Example: correct usage"
    )
    assert (
        spec.properties.get("inappropriate_tool_use_examples")
        == "Example: incorrect usage"
    )


def test_spec_with_desired_behaviour_properties(sample_task):
    """Test creating a spec with DesiredBehaviourProperties."""
    properties = DesiredBehaviourProperties(
        spec_type=SpecType.desired_behaviour,
        base_instruction="Test instruction",
        desired_behaviour_description="Avoid toxic language",
        correct_behaviour_examples="Example 1: Be polite and respectful",
        incorrect_behaviour_examples="Example 1: Don't use slurs\nExample 2: Don't be rude",
    )
    spec = Spec(
        name="Desired Behaviour Spec",
        definition="Test desired behaviour spec",
        properties=properties,
        parent=sample_task,
    )

    assert spec.properties is not None
    assert isinstance(spec.properties, dict)
    assert spec.properties["spec_type"] == SpecType.desired_behaviour
    assert spec.properties["desired_behaviour_description"] == "Avoid toxic language"
    assert (
        spec.properties.get("correct_behaviour_examples")
        == "Example 1: Be polite and respectful"
    )
    assert (
        spec.properties.get("incorrect_behaviour_examples")
        == "Example 1: Don't use slurs\nExample 2: Don't be rude"
    )


def test_spec_properties_validation_missing_required_fields(sample_task):
    """Test that properties validation fails with missing required fields."""
    with pytest.raises(ValidationError) as exc_info:
        properties = {
            "spec_type": SpecType.appropriate_tool_use,
            "base_instruction": "Test instruction",
            "tool_function_name": "tool_function_123",
        }
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,  # type: ignore[arg-type]
            parent=sample_task,
        )
    assert "Field required" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        properties = {
            "spec_type": SpecType.desired_behaviour,
            "base_instruction": "Test instruction",
        }
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,  # type: ignore[arg-type]
            parent=sample_task,
        )
    assert "Field required" in str(exc_info.value)


def test_spec_properties_validation_wrong_spec_type(sample_task):
    """Test that properties validation fails with wrong spec_type literal."""
    with pytest.raises(ValidationError):
        properties = AppropriateToolUseProperties(
            spec_type="wrong_type",  # type: ignore[arg-type]
            base_instruction="Test instruction",
            tool_function_name="tool_function_123",
            tool_use_guidelines="Use the tool when needed",
            appropriate_tool_use_examples="Example: correct",
            inappropriate_tool_use_examples="Example: incorrect",
        )
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,
            parent=sample_task,
        )

    with pytest.raises(ValidationError):
        properties = DesiredBehaviourProperties(
            spec_type="wrong_type",  # type: ignore[arg-type]
            base_instruction="Test instruction",
            desired_behaviour_description="Avoid toxic language",
        )
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,
            parent=sample_task,
        )


def test_spec_rejects_empty_dict_properties(sample_task):
    """Test that empty dict for properties is rejected by Pydantic validation."""
    with pytest.raises(ValidationError) as _exc_info:
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties={},  # type: ignore[arg-type]
            parent=sample_task,
        )


def test_spec_with_properties_and_definition(sample_task):
    """Test that definition field works correctly with properties."""
    properties = AppropriateToolUseProperties(
        spec_type=SpecType.appropriate_tool_use,
        base_instruction="Test instruction",
        tool_id="tool_123",
        tool_function_name="tool_function_123",
        tool_use_guidelines="Use the tool when needed",
        appropriate_tool_use_examples="Example: correct tool usage",
        inappropriate_tool_use_examples="Example: incorrect tool usage",
    )
    spec = Spec(
        name="Tool Use Spec",
        definition="This spec defines when to use tools appropriately",
        properties=properties,
        parent=sample_task,
    )

    assert spec.definition == "This spec defines when to use tools appropriately"
    assert spec.properties is not None
    assert spec.properties["spec_type"] == SpecType.appropriate_tool_use
    assert spec.properties["tool_function_name"] == "tool_function_123"  # type: ignore[literal-required]
