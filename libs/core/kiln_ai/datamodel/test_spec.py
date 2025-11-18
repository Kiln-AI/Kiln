import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.spec import Spec, SpecPriority, SpecStatus, SpecType
from kiln_ai.datamodel.task import Task


@pytest.fixture
def sample_task():
    return Task(name="Test Task", instruction="Test instruction")


def test_spec_valid_creation(sample_task):
    """Test creating a spec with all required fields."""
    spec = Spec(
        name="Test Spec",
        definition="The system should behave correctly",
        type=SpecType.desired_behaviour,
        parent=sample_task,
    )

    assert spec.name == "Test Spec"
    assert spec.definition == "The system should behave correctly"
    assert spec.type == SpecType.desired_behaviour
    assert spec.priority == SpecPriority.high
    assert spec.status == SpecStatus.not_started
    assert spec.tags == []
    assert spec.eval_id is None


def test_spec_with_custom_values(sample_task):
    """Test creating a spec with custom priority, status, and tags."""
    spec = Spec(
        name="Custom Spec",
        definition="No toxic content should be present",
        type=SpecType.toxicity,
        priority=SpecPriority.low,
        status=SpecStatus.in_progress,
        tags=["tag1", "tag2"],
        eval_id="test_eval_id",
        parent=sample_task,
    )

    assert spec.priority == SpecPriority.low
    assert spec.status == SpecStatus.in_progress
    assert spec.tags == ["tag1", "tag2"]
    assert spec.eval_id == "test_eval_id"


def test_spec_missing_required_fields(sample_task):
    """Test that spec creation fails without required fields."""
    # Missing name
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            definition="Test definition",
            type=SpecType.desired_behaviour,
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing definition
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
            definition="Test definition",
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)


def test_spec_empty_name(sample_task):
    """Test that spec creation fails with empty name."""
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="",
            definition="Test definition",
            type=SpecType.desired_behaviour,
            parent=sample_task,
        )
    assert "Name is too short" in str(exc_info.value)


def test_spec_empty_definition(sample_task):
    """Test that spec creation fails with empty definition."""
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            definition="",
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
        definition="Test definition",
        type=spec_type,
        parent=sample_task,
    )
    assert spec.type == spec_type


@pytest.mark.parametrize(
    "priority",
    [SpecPriority.low, SpecPriority.medium, SpecPriority.high],
)
def test_spec_all_priorities(sample_task, priority):
    """Test that all priority levels can be set."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        type=SpecType.desired_behaviour,
        priority=priority,
        parent=sample_task,
    )
    assert spec.priority == priority


@pytest.mark.parametrize(
    "status",
    [
        SpecStatus.deprecated,
        SpecStatus.not_started,
        SpecStatus.in_progress,
        SpecStatus.complete,
    ],
)
def test_spec_all_statuses(sample_task, status):
    """Test that all status values can be set."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
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
            definition="Test definition",
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
            definition="Test definition",
            type=SpecType.desired_behaviour,
            tags=["valid_tag", "invalid tag"],
            parent=sample_task,
        )


def test_spec_tags_valid(sample_task):
    """Test that valid tags work correctly."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        type=SpecType.desired_behaviour,
        tags=["tag1", "tag_2", "tag-3", "TAG4"],
        parent=sample_task,
    )
    assert spec.tags == ["tag1", "tag_2", "tag-3", "TAG4"]
