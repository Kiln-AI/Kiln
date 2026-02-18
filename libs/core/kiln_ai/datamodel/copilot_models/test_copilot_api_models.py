import pytest
from kiln_ai.datamodel.copilot_models.copilot_api_models import (
    ClarifySpecInput,
    ClarifySpecOutput,
    ExamplesForFeedbackItem,
    ExamplesWithFeedbackItem,
    GenerateBatchInput,
    GenerateBatchOutput,
    RefineSpecInput,
    ReviewedExample,
    Sample,
    SpecificationInput,
    SyntheticDataGenerationSessionConfig,
    SyntheticDataGenerationSessionConfigInput,
    SyntheticDataGenerationStepConfig,
    SyntheticDataGenerationStepConfigInput,
    TaskInfo,
    TaskMetadata,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from pydantic import ValidationError


class TestTaskInfo:
    def test_creates_with_required_fields(self):
        info = TaskInfo(
            task_prompt="Test prompt",
            task_input_schema='{"type": "string"}',
            task_output_schema='{"type": "object"}',
        )
        assert info.task_prompt == "Test prompt"
        assert info.task_input_schema == '{"type": "string"}'
        assert info.task_output_schema == '{"type": "object"}'

    def test_missing_required_field_raises_error(self):
        with pytest.raises(ValidationError):
            TaskInfo(
                task_input_schema='{"type": "string"}',
            )

    def test_optional_schemas_default_to_none(self):
        info = TaskInfo(
            task_prompt="Test prompt",
        )
        assert info.task_input_schema is None
        assert info.task_output_schema is None


class TestTaskMetadata:
    def test_creates_with_required_fields(self):
        metadata = TaskMetadata(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
        )
        assert metadata.model_name == "gpt-4"
        assert metadata.model_provider_name == ModelProviderName.openai

    def test_accepts_valid_provider_names(self):
        for provider in [
            ModelProviderName.openai,
            ModelProviderName.anthropic,
            ModelProviderName.groq,
        ]:
            metadata = TaskMetadata(
                model_name="test-model",
                model_provider_name=provider,
            )
            assert metadata.model_provider_name == provider


class TestSyntheticDataGenerationStepConfig:
    def test_creates_with_required_fields(self):
        metadata = TaskMetadata(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
        )
        result = SyntheticDataGenerationStepConfig(
            task_metadata=metadata,
            prompt="Generated prompt content",
        )
        assert result.task_metadata.model_name == "gpt-4"
        assert result.prompt == "Generated prompt content"


class TestSample:
    def test_creates_with_required_fields(self):
        sample = Sample(input="test input", output="test output")
        assert sample.input == "test input"
        assert sample.output == "test output"


class TestReviewedExample:
    def test_creates_with_required_fields(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=False,
            feedback="User disagrees",
        )
        assert example.input == "test input"
        assert example.output == "test output"
        assert example.model_says_meets_spec is True
        assert example.user_says_meets_spec is False
        assert example.feedback == "User disagrees"


class TestSpecificationInput:
    def test_creates_with_required_fields(self):
        info = SpecificationInput(
            spec_fields={"field1": "Field 1 description"},
            spec_field_current_values={"field1": "current value"},
        )
        assert info.spec_fields == {"field1": "Field 1 description"}
        assert info.spec_field_current_values == {"field1": "current value"}

    def test_accepts_empty_dicts(self):
        info = SpecificationInput(
            spec_fields={},
            spec_field_current_values={},
        )
        assert info.spec_fields == {}
        assert info.spec_field_current_values == {}


class TestExamplesWithFeedbackItem:
    def test_creates_with_required_fields(self):
        example = ExamplesWithFeedbackItem(
            user_agrees_with_judge=True,
            input="test input",
            output="test output",
            fails_specification=False,
        )
        assert example.user_agrees_with_judge is True
        assert example.input == "test input"
        assert example.output == "test output"
        assert example.fails_specification is False

    def test_user_feedback_optional(self):
        example = ExamplesWithFeedbackItem(
            user_agrees_with_judge=True,
            input="test input",
            output="test output",
            fails_specification=False,
        )
        assert example.user_feedback is None

    def test_user_feedback_can_be_set(self):
        example = ExamplesWithFeedbackItem(
            user_agrees_with_judge=False,
            input="test input",
            output="test output",
            fails_specification=True,
            user_feedback="This is wrong because...",
        )
        assert example.user_feedback == "This is wrong because..."


class TestClarifySpecInput:
    def test_creates_with_required_fields(self):
        task_info = TaskInfo(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        input_model = ClarifySpecInput(
            target_task_info=task_info,
            target_specification="Test spec",
            num_samples_per_topic=5,
            num_topics=3,
            providers=[ModelProviderName.openai],
        )
        assert input_model.target_specification == "Test spec"
        assert input_model.num_samples_per_topic == 5
        assert input_model.num_topics == 3
        assert input_model.num_exemplars == 10

    def test_num_exemplars_default_value(self):
        task_info = TaskInfo(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        input_model = ClarifySpecInput(
            target_task_info=task_info,
            target_specification="Test spec",
            num_samples_per_topic=5,
            num_topics=3,
            providers=[ModelProviderName.openai],
        )
        assert input_model.num_exemplars == 10


class TestRefineSpecInput:
    def test_creates_with_required_fields(self):
        task_info = TaskInfo(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        spec_info = SpecificationInput(
            spec_fields={"field": "description"},
            spec_field_current_values={"field": "value"},
        )
        example = ExamplesWithFeedbackItem(
            user_agrees_with_judge=True,
            input="test",
            output="output",
            fails_specification=False,
        )
        input_model = RefineSpecInput(
            target_task_info=task_info,
            target_specification=spec_info,
            examples_with_feedback=[example],
        )
        assert len(input_model.examples_with_feedback) == 1


class TestGenerateBatchInput:
    def test_creates_with_required_fields(self):
        task_info = TaskInfo(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        input_model = GenerateBatchInput(
            target_task_info=task_info,
            sdg_session_config=SyntheticDataGenerationSessionConfigInput(
                topic_generation_config=SyntheticDataGenerationStepConfigInput(
                    task_metadata=TaskMetadata(
                        model_name="gpt-4",
                        model_provider_name=ModelProviderName.openai,
                    ),
                    prompt="Test prompt",
                ),
                input_generation_config=SyntheticDataGenerationStepConfigInput(
                    task_metadata=TaskMetadata(
                        model_name="gpt-4",
                        model_provider_name=ModelProviderName.openai,
                    ),
                    prompt="Test prompt",
                ),
                output_generation_config=SyntheticDataGenerationStepConfigInput(
                    task_metadata=TaskMetadata(
                        model_name="gpt-4",
                        model_provider_name=ModelProviderName.openai,
                    ),
                    prompt="Test prompt",
                ),
            ),
            target_specification="Test spec",
            num_samples_per_topic=5,
            num_topics=3,
        )
        assert (
            input_model.sdg_session_config.topic_generation_config.prompt
            == "Test prompt"
        )
        assert (
            input_model.sdg_session_config.input_generation_config.prompt
            == "Test prompt"
        )
        assert (
            input_model.sdg_session_config.output_generation_config.prompt
            == "Test prompt"
        )
        assert input_model.target_specification == "Test spec"
        assert input_model.num_samples_per_topic == 5
        assert input_model.num_topics == 3


class TestClarifySpecOutput:
    def test_creates_with_required_fields(self):
        metadata = TaskMetadata(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
        )
        prompt_result = SyntheticDataGenerationStepConfig(
            task_metadata=metadata,
            prompt="Test prompt",
        )
        example = ExamplesForFeedbackItem(
            input="test",
            output="output",
            fails_specification=False,
        )
        output = ClarifySpecOutput(
            examples_for_feedback=[example],
            judge_result=prompt_result,
            sdg_session_config=SyntheticDataGenerationSessionConfig(
                topic_generation_config=prompt_result,
                input_generation_config=prompt_result,
                output_generation_config=prompt_result,
            ),
        )
        assert len(output.examples_for_feedback) == 1
        assert output.judge_result.prompt == "Test prompt"


class TestGenerateBatchOutput:
    def test_creates_with_required_fields(self):
        sample = Sample(input="test", output="output")
        output = GenerateBatchOutput(
            data_by_topic={"topic1": [sample]},
        )
        assert "topic1" in output.data_by_topic
        assert len(output.data_by_topic["topic1"]) == 1

    def test_accepts_empty_data_by_topic(self):
        output = GenerateBatchOutput(data_by_topic={})
        assert output.data_by_topic == {}
