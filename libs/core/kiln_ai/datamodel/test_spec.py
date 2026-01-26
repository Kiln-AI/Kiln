import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.spec import PromptGenerationInfo, Spec, SpecStatus, TaskSample
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
        core_requirement="Test instruction",
        tone_description="Professional and friendly",
    )


def test_spec_valid_creation(sample_task):
    """Test creating a spec with all required fields."""
    properties = ToneProperties(
        spec_type=SpecType.tone,
        core_requirement="Test instruction",
        tone_description="Professional and friendly",
    )
    spec = Spec(
        name="Test Spec",
        definition="The system should behave correctly",
        properties=properties,
        eval_id="test_eval_id",
        parent=sample_task,
    )

    assert spec.name == "Test Spec"
    assert spec.definition == "The system should behave correctly"
    assert spec.properties["spec_type"] == SpecType.tone
    assert spec.priority == Priority.p1
    assert spec.status == SpecStatus.active
    assert spec.tags == []
    assert spec.eval_id == "test_eval_id"
    assert spec.task_sample is None


def test_spec_with_custom_values(sample_task):
    """Test creating a spec with custom priority, status, and tags."""
    properties = ToxicityProperties(
        spec_type=SpecType.toxicity,
        core_requirement="Test instruction",
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
            eval_id="test_eval_id",
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing definition
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            properties=sample_tone_properties,
            eval_id="test_eval_id",
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing properties
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            definition="Test definition",
            eval_id="test_eval_id",
            parent=sample_task,
        )  # type: ignore
    assert "Field required" in str(exc_info.value)

    # Missing eval_id
    with pytest.raises(ValidationError) as exc_info:
        Spec(
            name="Test",
            definition="Test definition",
            properties=sample_tone_properties,
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
            eval_id="test_eval_id",
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
            eval_id="test_eval_id",
            parent=sample_task,
        )
    assert "String should have at least 1 character" in str(exc_info.value)


def create_sample_properties(spec_type: SpecType):
    """Helper to create sample properties for testing."""
    core_requirement = "Test instruction"

    if spec_type == SpecType.desired_behaviour:
        return DesiredBehaviourProperties(
            spec_type=spec_type,
            desired_behaviour_description="Test desired behaviour",
        )
    elif spec_type == SpecType.issue:
        return IssueProperties(
            spec_type=spec_type,
            issue_description="Test issue description",
        )
    elif spec_type == SpecType.tone:
        return ToneProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            tone_description="Professional",
        )
    elif spec_type == SpecType.formatting:
        return FormattingProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            formatting_requirements="Use markdown",
        )
    elif spec_type == SpecType.localization:
        return LocalizationProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            localization_requirements="Support en-US",
            violation_examples="Example: using wrong language",
        )
    elif spec_type == SpecType.appropriate_tool_use:
        return AppropriateToolUseProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            tool_id="test_tool_id",
            tool_function_name="test_tool",
            tool_use_guidelines="Use when needed",
            appropriate_tool_use_examples="Example: correct tool usage",
            inappropriate_tool_use_examples="Example: incorrect tool usage",
        )
    elif spec_type == SpecType.reference_answer_accuracy:
        return ReferenceAnswerAccuracyProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            reference_answer_accuracy_description="Must match reference",
            accurate_examples="Example: accurate answer",
            inaccurate_examples="Example: inaccurate answer",
        )
    elif spec_type == SpecType.factual_correctness:
        return FactualCorrectnessProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            factually_inaccurate_examples="Example: wrong date",
        )
    elif spec_type == SpecType.hallucinations:
        return HallucinationsProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            hallucinations_examples="Example: made up fact",
        )
    elif spec_type == SpecType.completeness:
        return CompletenessProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            complete_examples="Example: complete answer",
            incomplete_examples="Example: incomplete answer",
        )
    elif spec_type == SpecType.toxicity:
        return ToxicityProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            toxicity_examples="Example: offensive language",
        )
    elif spec_type == SpecType.bias:
        return BiasProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            bias_examples="Example: biased statement",
        )
    elif spec_type == SpecType.maliciousness:
        return MaliciousnessProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            malicious_examples="Example: harmful advice",
        )
    elif spec_type == SpecType.nsfw:
        return NsfwProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            nsfw_examples="Example: inappropriate content",
        )
    elif spec_type == SpecType.taboo:
        return TabooProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            taboo_examples="Example: taboo content",
        )
    elif spec_type == SpecType.jailbreak:
        return JailbreakProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
            jailbroken_examples="Example: bypassing safety",
        )
    elif spec_type == SpecType.prompt_leakage:
        return PromptLeakageProperties(
            spec_type=spec_type,
            core_requirement=core_requirement,
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
        eval_id="test_eval_id",
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
        eval_id="test_eval_id",
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
        eval_id="test_eval_id",
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
            eval_id="test_eval_id",
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
            eval_id="test_eval_id",
            parent=sample_task,
        )


def test_spec_tags_valid(sample_task, sample_tone_properties):
    """Test that valid tags work correctly."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        tags=["tag1", "tag_2", "tag-3", "TAG4"],
        eval_id="test_eval_id",
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
        eval_id="test_eval_id",
        parent=sample_task,
    )
    assert spec.status == SpecStatus.archived

    spec2 = Spec(
        name="Test Spec 2",
        definition="Test definition",
        properties=sample_tone_properties,
        status=SpecStatus.active,
        eval_id="test_eval_id_2",
        parent=sample_task,
    )
    assert spec2.status == SpecStatus.active


def test_spec_with_appropriate_tool_use_properties(sample_task):
    """Test creating a spec with AppropriateToolUseProperties."""
    properties = AppropriateToolUseProperties(
        spec_type=SpecType.appropriate_tool_use,
        core_requirement="Test instruction",
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
        eval_id="test_eval_id",
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
        core_requirement="Test instruction",
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
        eval_id="test_eval_id",
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
        desired_behaviour_description="Avoid toxic language",
        correct_behaviour_examples="Example 1: Be polite and respectful",
        incorrect_behaviour_examples="Example 1: Don't use slurs\nExample 2: Don't be rude",
    )
    spec = Spec(
        name="Desired Behaviour Spec",
        definition="Test desired behaviour spec",
        properties=properties,
        eval_id="test_eval_id",
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
            "core_requirement": "Test instruction",
            "tool_function_name": "tool_function_123",
        }
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,  # type: ignore[arg-type]
            eval_id="test_eval_id",
            parent=sample_task,
        )
    assert "Field required" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        properties = {
            "spec_type": SpecType.desired_behaviour,
            "core_requirement": "Test instruction",
        }
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,  # type: ignore[arg-type]
            eval_id="test_eval_id",
            parent=sample_task,
        )
    assert "Field required" in str(exc_info.value)


def test_spec_properties_validation_wrong_spec_type(sample_task):
    """Test that properties validation fails with wrong spec_type literal."""
    with pytest.raises(ValidationError):
        properties = AppropriateToolUseProperties(
            spec_type="wrong_type",  # type: ignore[arg-type]
            core_requirement="Test instruction",
            tool_function_name="tool_function_123",
            tool_use_guidelines="Use the tool when needed",
            appropriate_tool_use_examples="Example: correct",
            inappropriate_tool_use_examples="Example: incorrect",
        )
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,
            eval_id="test_eval_id",
            parent=sample_task,
        )

    with pytest.raises(ValidationError):
        properties = DesiredBehaviourProperties(
            spec_type="wrong_type",  # type: ignore[arg-type]
            desired_behaviour_description="Avoid toxic language",
        )
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties=properties,
            eval_id="test_eval_id",
            parent=sample_task,
        )


def test_spec_rejects_empty_dict_properties(sample_task):
    """Test that empty dict for properties is rejected by Pydantic validation."""
    with pytest.raises(ValidationError) as _exc_info:
        Spec(
            name="Test Spec",
            definition="Test definition",
            properties={},  # type: ignore[arg-type]
            eval_id="test_eval_id",
            parent=sample_task,
        )


def test_spec_with_properties_and_definition(sample_task):
    """Test that definition field works correctly with properties."""
    properties = AppropriateToolUseProperties(
        spec_type=SpecType.appropriate_tool_use,
        core_requirement="Test instruction",
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
        eval_id="test_eval_id",
        parent=sample_task,
    )

    assert spec.definition == "This spec defines when to use tools appropriately"
    assert spec.properties is not None
    assert spec.properties["spec_type"] == SpecType.appropriate_tool_use
    assert spec.properties["tool_function_name"] == "tool_function_123"  # type: ignore[literal-required]


def test_task_sample_model():
    """Test creating a TaskSample model."""
    sample = TaskSample(
        input="What is the capital of France?",
        output="The capital of France is Paris.",
    )
    assert sample.input == "What is the capital of France?"
    assert sample.output == "The capital of France is Paris."


def test_spec_with_task_sample(sample_task, sample_tone_properties):
    """Test creating a spec with a task sample."""
    sample = TaskSample(
        input="Example input",
        output="Example output",
    )
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        eval_id="test_eval_id",
        task_sample=sample,
        parent=sample_task,
    )
    assert spec.task_sample is not None
    assert spec.task_sample.input == "Example input"
    assert spec.task_sample.output == "Example output"


def test_spec_without_task_sample(sample_task, sample_tone_properties):
    """Test that task_sample defaults to None."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        eval_id="test_eval_id",
        parent=sample_task,
    )
    assert spec.task_sample is None


def test_spec_task_sample_serialization(sample_tone_properties, tmp_path):
    """Test that task_sample is properly serialized and deserialized."""
    from kiln_ai.datamodel import Project

    project_path = tmp_path / "project.kiln"
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    task = Task(name="Test Task", instruction="Test instruction", parent=project)
    task.save_to_file()

    sample = TaskSample(
        input="Serialize me",
        output="I am serialized",
    )
    spec = Spec(
        name="Serialization Test",
        definition="Test definition",
        properties=sample_tone_properties,
        eval_id="test_eval_id",
        task_sample=sample,
        parent=task,
    )
    spec.save_to_file()

    loaded_spec = Spec.from_id_and_parent_path(spec.id, task.path)
    assert loaded_spec is not None
    assert loaded_spec.task_sample is not None
    assert loaded_spec.task_sample.input == "Serialize me"
    assert loaded_spec.task_sample.output == "I am serialized"


def test_prompt_generation_info_model():
    """Test creating a PromptGenerationInfo model."""
    info = PromptGenerationInfo(
        model_name="gpt-4",
        provider_name="openai",
        prompt="Generate topics for testing",
    )
    assert info.model_name == "gpt-4"
    assert info.provider_name == "openai"
    assert info.prompt == "Generate topics for testing"


def test_spec_with_generation_info(sample_task, sample_tone_properties):
    """Test creating a spec with topic and input generation info."""
    topic_info = PromptGenerationInfo(
        model_name="gpt-4",
        provider_name="openai",
        prompt="Generate topics",
    )
    input_info = PromptGenerationInfo(
        model_name="claude-3",
        provider_name="anthropic",
        prompt="Generate inputs",
    )
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        eval_id="test_eval_id",
        topic_generation_info=topic_info,
        input_generation_info=input_info,
        parent=sample_task,
    )
    assert spec.topic_generation_info is not None
    assert spec.topic_generation_info.model_name == "gpt-4"
    assert spec.topic_generation_info.provider_name == "openai"
    assert spec.topic_generation_info.prompt == "Generate topics"
    assert spec.input_generation_info is not None
    assert spec.input_generation_info.model_name == "claude-3"
    assert spec.input_generation_info.provider_name == "anthropic"
    assert spec.input_generation_info.prompt == "Generate inputs"


def test_spec_without_generation_info(sample_task, sample_tone_properties):
    """Test that generation info fields default to None."""
    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        properties=sample_tone_properties,
        eval_id="test_eval_id",
        parent=sample_task,
    )
    assert spec.topic_generation_info is None
    assert spec.input_generation_info is None


def test_spec_generation_info_serialization(sample_tone_properties, tmp_path):
    """Test that generation info is properly serialized and deserialized."""
    from kiln_ai.datamodel import Project

    project_path = tmp_path / "project.kiln"
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    task = Task(name="Test Task", instruction="Test instruction", parent=project)
    task.save_to_file()

    topic_info = PromptGenerationInfo(
        model_name="gpt-4",
        provider_name="openai",
        prompt="Topic generation prompt",
    )
    input_info = PromptGenerationInfo(
        model_name="claude-3",
        provider_name="anthropic",
        prompt="Input generation prompt",
    )
    spec = Spec(
        name="Generation Info Test",
        definition="Test definition",
        properties=sample_tone_properties,
        eval_id="test_eval_id",
        topic_generation_info=topic_info,
        input_generation_info=input_info,
        parent=task,
    )
    spec.save_to_file()

    loaded_spec = Spec.from_id_and_parent_path(spec.id, task.path)
    assert loaded_spec is not None
    assert loaded_spec.topic_generation_info is not None
    assert loaded_spec.topic_generation_info.model_name == "gpt-4"
    assert loaded_spec.topic_generation_info.provider_name == "openai"
    assert loaded_spec.topic_generation_info.prompt == "Topic generation prompt"
    assert loaded_spec.input_generation_info is not None
    assert loaded_spec.input_generation_info.model_name == "claude-3"
    assert loaded_spec.input_generation_info.provider_name == "anthropic"
    assert loaded_spec.input_generation_info.prompt == "Input generation prompt"
