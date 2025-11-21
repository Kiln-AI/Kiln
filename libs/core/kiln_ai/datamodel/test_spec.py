import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.spec import Spec, SpecStatus, SpecType
from kiln_ai.datamodel.spec_properties import (
    AppropriateToolUseProperties,
    UndesiredBehaviourProperties,
)
from kiln_ai.datamodel.task import Task


@pytest.fixture
def sample_task():
    return Task(name="Test Task", instruction="Test instruction")


def test_spec_valid_creation(sample_task):
    """Test creating a spec with all required fields."""
    spec = Spec(
        name="Test Spec",
        description="The system should behave correctly",
        type=SpecType.desired_behaviour,
        parent=sample_task,
    )

    assert spec.name == "Test Spec"
    assert spec.description == "The system should behave correctly"
    assert spec.type == SpecType.desired_behaviour
    assert spec.priority == Priority.p1
    assert spec.status == SpecStatus.active
    assert spec.tags == []
    assert spec.eval_id is None


def test_spec_with_custom_values(sample_task):
    """Test creating a spec with custom priority, status, and tags."""
    spec = Spec(
        name="Custom Spec",
        description="No toxic content should be present",
        type=SpecType.toxicity,
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


def test_spec_missing_required_fields(sample_task):
    """Test that spec creation fails without required fields."""
    # Missing name
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            description="Test description",
            type=SpecType.desired_behaviour,
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing description
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            type=SpecType.desired_behaviour,
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing type
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            description="Test description",
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)


def test_spec_empty_name(sample_task):
    """Test that spec creation fails with empty name."""
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="",
            description="Test description",
            type=SpecType.desired_behaviour,
            parent=sample_task,
        )
    assert "Name is too short" in str(exc_info.value)


def test_spec_empty_description(sample_task):
    """Test that spec creation fails with empty description."""
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            description="",
            type=SpecType.desired_behaviour,
            parent=sample_task,
        )
    assert "String should have at least 1 character" in str(exc_info.value)


@pytest.mark.parametrize(
    "spec_type",
    [
        SpecType.desired_behaviour,
        SpecType.undesired_behaviour,
        SpecType.appropriate_tool_use,
        SpecType.intermediate_reasoning,
        SpecType.reference_answer_accuracy,
        SpecType.factual_correctness,
        SpecType.hallucinations,
        SpecType.completeness,
        SpecType.consistency,
        SpecType.tone,
        SpecType.formatting,
        SpecType.localization,
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
    spec = Spec(
        name="Test Spec",
        description="Test description",
        type=spec_type,
        parent=sample_task,
    )
    assert spec.type == spec_type


@pytest.mark.parametrize(
    "priority",
    [Priority.p0, Priority.p1, Priority.p2, Priority.p3],
)
def test_spec_all_priorities(sample_task, priority):
    """Test that all priority levels can be set."""
    spec = Spec(
        name="Test Spec",
        description="Test description",
        type=SpecType.desired_behaviour,
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
def test_spec_all_statuses(sample_task, status):
    """Test that all status values can be set."""
    spec = Spec(
        name="Test Spec",
        description="Test description",
        type=SpecType.desired_behaviour,
        status=status,
        parent=sample_task,
    )
    assert spec.status == status


def test_spec_tags_validation_empty_string(sample_task):
    """Test that tags cannot be empty strings."""
    with pytest.raises(ValidationError, match="tags cannot be empty strings"):
        Spec(
            name="Test Spec",
            description="Test description",
            type=SpecType.desired_behaviour,
            tags=["valid_tag", ""],
            parent=sample_task,
        )


def test_spec_tags_validation_spaces(sample_task):
    """Test that tags cannot contain spaces."""
    with pytest.raises(
        ValidationError, match=r"tags cannot contain spaces\. Try underscores\."
    ):
        Spec(
            name="Test Spec",
            description="Test description",
            type=SpecType.desired_behaviour,
            tags=["valid_tag", "invalid tag"],
            parent=sample_task,
        )


def test_spec_tags_valid(sample_task):
    """Test that valid tags work correctly."""
    spec = Spec(
        name="Test Spec",
        description="Test description",
        type=SpecType.desired_behaviour,
        tags=["tag1", "tag_2", "tag-3", "TAG4"],
        parent=sample_task,
    )
    assert spec.tags == ["tag1", "tag_2", "tag-3", "TAG4"]


def test_spec_archived_status(sample_task):
    """Test that archived status works correctly."""
    spec = Spec(
        name="Test Spec",
        description="Test description",
        type=SpecType.desired_behaviour,
        status=SpecStatus.archived,
        parent=sample_task,
    )
    assert spec.status == SpecStatus.archived

    spec2 = Spec(
        name="Test Spec 2",
        description="Test description",
        type=SpecType.desired_behaviour,
        status=SpecStatus.active,
        parent=sample_task,
    )
    assert spec2.status == SpecStatus.active


def test_spec_with_none_properties(sample_task):
    """Test that specs can be created with None properties."""
    spec = Spec(
        name="Test Spec",
        description="Test description",
        type=SpecType.desired_behaviour,
        properties=None,
        parent=sample_task,
    )
    assert spec.properties is None


def test_spec_with_appropriate_tool_use_properties(sample_task):
    """Test creating a spec with AppropriateToolUseProperties."""
    properties = AppropriateToolUseProperties(
        spec_type="appropriate_tool_use",
        tool_id="tool-123",
        appropriate_tool_use_guidelines="Use the tool when needed",
        inappropriate_tool_use_guidelines="Don't use for simple queries",
    )
    spec = Spec(
        name="Tool Use Spec",
        description="Test tool use spec",
        type=SpecType.appropriate_tool_use,
        properties=properties,
        parent=sample_task,
    )

    assert spec.properties is not None
    assert isinstance(spec.properties, dict)
    assert spec.properties["spec_type"] == "appropriate_tool_use"
    assert spec.properties["tool_id"] == "tool-123"
    assert (
        spec.properties["appropriate_tool_use_guidelines"] == "Use the tool when needed"
    )
    assert (
        spec.properties["inappropriate_tool_use_guidelines"]
        == "Don't use for simple queries"
    )


def test_spec_with_appropriate_tool_use_properties_optional_field(sample_task):
    """Test creating a spec with AppropriateToolUseProperties without optional field."""
    properties = AppropriateToolUseProperties(
        spec_type="appropriate_tool_use",
        tool_id="tool-456",
        appropriate_tool_use_guidelines="Use the tool when needed",
        inappropriate_tool_use_guidelines=None,
    )
    spec = Spec(
        name="Tool Use Spec",
        description="Test tool use spec",
        type=SpecType.appropriate_tool_use,
        properties=properties,
        parent=sample_task,
    )

    assert spec.properties is not None
    assert isinstance(spec.properties, dict)
    assert spec.properties.get("inappropriate_tool_use_guidelines") is None


def test_spec_with_undesired_behaviour_properties(sample_task):
    """Test creating a spec with UndesiredBehaviourProperties."""
    properties = UndesiredBehaviourProperties(
        spec_type="undesired_behaviour",
        undesired_behaviour_guidelines="Avoid toxic language",
        examples="Example 1: Don't use slurs\nExample 2: Don't be rude",
    )
    spec = Spec(
        name="Undesired Behaviour Spec",
        description="Test undesired behaviour spec",
        type=SpecType.undesired_behaviour,
        properties=properties,
        parent=sample_task,
    )

    assert spec.properties is not None
    assert isinstance(spec.properties, dict)
    assert spec.properties["spec_type"] == "undesired_behaviour"
    assert spec.properties["undesired_behaviour_guidelines"] == "Avoid toxic language"
    assert (
        spec.properties["examples"]
        == "Example 1: Don't use slurs\nExample 2: Don't be rude"
    )


def test_spec_type_matches_properties_appropriate_tool_use(sample_task):
    """Test that the validator ensures type matches properties for appropriate_tool_use."""
    properties = AppropriateToolUseProperties(
        spec_type="appropriate_tool_use",
        tool_id="tool-123",
        appropriate_tool_use_guidelines="Use the tool when needed",
        inappropriate_tool_use_guidelines=None,
    )
    spec = Spec(
        name="Tool Use Spec",
        description="Test tool use spec",
        type=SpecType.appropriate_tool_use,
        properties=properties,
        parent=sample_task,
    )

    assert spec.type == SpecType.appropriate_tool_use
    assert spec.properties is not None
    assert spec.properties["spec_type"] == "appropriate_tool_use"


def test_spec_type_matches_properties_undesired_behaviour(sample_task):
    """Test that the validator ensures type matches properties for undesired_behaviour."""
    properties = UndesiredBehaviourProperties(
        spec_type="undesired_behaviour",
        undesired_behaviour_guidelines="Avoid toxic language",
        examples="Example text",
    )
    spec = Spec(
        name="Undesired Behaviour Spec",
        description="Test undesired behaviour spec",
        type=SpecType.undesired_behaviour,
        properties=properties,
        parent=sample_task,
    )

    assert spec.type == SpecType.undesired_behaviour
    assert spec.properties is not None
    assert spec.properties["spec_type"] == "undesired_behaviour"


def test_spec_type_mismatch_with_properties_raises_error(sample_task):
    """Test that creating a spec with mismatched type and properties raises an error."""
    properties = AppropriateToolUseProperties(
        spec_type="appropriate_tool_use",
        tool_id="tool-123",
        appropriate_tool_use_guidelines="Use the tool when needed",
        inappropriate_tool_use_guidelines=None,
    )

    with pytest.raises(ValueError, match="Spec type mismatch"):
        Spec(
            name="Mismatched Spec",
            description="Test spec with mismatched type",
            type=SpecType.undesired_behaviour,
            properties=properties,
            parent=sample_task,
        )


def test_spec_type_mismatch_with_properties_reverse(sample_task):
    """Test that creating a spec with mismatched type and properties raises an error (reverse)."""
    properties = UndesiredBehaviourProperties(
        spec_type="undesired_behaviour",
        undesired_behaviour_guidelines="Avoid toxic language",
        examples="Example text",
    )

    with pytest.raises(ValueError, match="Spec type mismatch"):
        Spec(
            name="Mismatched Spec",
            description="Test spec with mismatched type",
            type=SpecType.appropriate_tool_use,
            properties=properties,
            parent=sample_task,
        )


def test_spec_properties_validation_missing_required_fields(sample_task):
    """Test that properties validation fails with missing required fields."""
    with pytest.raises(ValidationError) as exc_info:
        # Intentionally missing required field to test validation
        properties = {
            "spec_type": "appropriate_tool_use",
            "tool_id": "tool-123",
        }
        Spec(
            name="Test Spec",
            description="Test description",
            type=SpecType.appropriate_tool_use,
            properties=properties,  # type: ignore[arg-type]
            parent=sample_task,
        )
    assert "Field required" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        # Intentionally missing required field to test validation
        properties = {
            "spec_type": "undesired_behaviour",
            "undesired_behaviour_guidelines": "Avoid toxic language",
        }
        Spec(
            name="Test Spec",
            description="Test description",
            type=SpecType.undesired_behaviour,
            properties=properties,  # type: ignore[arg-type]
            parent=sample_task,
        )
    assert "Field required" in str(exc_info.value)


def test_spec_properties_validation_wrong_spec_type(sample_task):
    """Test that properties validation fails with wrong spec_type literal."""
    with pytest.raises(ValidationError):
        # Intentionally using wrong spec_type to test validation
        properties = AppropriateToolUseProperties(
            spec_type="wrong_type",  # type: ignore[arg-type]
            tool_id="tool-123",
            appropriate_tool_use_guidelines="Use the tool when needed",
            inappropriate_tool_use_guidelines=None,
        )
        Spec(
            name="Test Spec",
            description="Test description",
            type=SpecType.appropriate_tool_use,
            properties=properties,
            parent=sample_task,
        )

    with pytest.raises(ValidationError):
        # Intentionally using wrong spec_type to test validation
        properties = UndesiredBehaviourProperties(
            spec_type="wrong_type",  # type: ignore[arg-type]
            undesired_behaviour_guidelines="Avoid toxic language",
            examples="Example text",
        )
        Spec(
            name="Test Spec",
            description="Test description",
            type=SpecType.undesired_behaviour,
            properties=properties,
            parent=sample_task,
        )


def test_spec_rejects_empty_dict_properties(sample_task):
    """Test that empty dict for properties is rejected by Pydantic validation."""
    with pytest.raises(ValidationError):
        Spec(
            name="Test Spec",
            description="Test description",
            type=SpecType.desired_behaviour,
            properties={},  # type: ignore[arg-type]
            parent=sample_task,
        )


def test_spec_with_properties_and_description(sample_task):
    """Test that description field works correctly with properties."""
    properties = AppropriateToolUseProperties(
        spec_type="appropriate_tool_use",
        tool_id="tool-123",
        appropriate_tool_use_guidelines="Use the tool when needed",
        inappropriate_tool_use_guidelines=None,
    )
    spec = Spec(
        name="Tool Use Spec",
        description="This spec defines when to use tools appropriately",
        type=SpecType.appropriate_tool_use,
        properties=properties,
        parent=sample_task,
    )

    assert spec.description == "This spec defines when to use tools appropriately"
    assert spec.properties is not None
    assert spec.properties["spec_type"] == "appropriate_tool_use"
    # Type checker doesn't know which variant of the union this is, but we verified spec_type above
    assert spec.properties["tool_id"] == "tool-123"  # type: ignore[literal-required]
