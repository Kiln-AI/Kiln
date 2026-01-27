"""Tests for app/desktop/studio_server/api_models/copilot_models.py."""

import pytest
from app.desktop.studio_server.api_models.copilot_models import (
    ClarifySpecApiInput,
    ClarifySpecApiOutput,
    ExampleWithFeedbackApi,
    GenerateBatchApiInput,
    GenerateBatchApiOutput,
    PromptGenerationResultApi,
    RefineSpecApiInput,
    ReviewedExample,
    SampleApi,
    SpecApi,
    SubsampleBatchOutputItemApi,
    TaskInfoApi,
    TaskMetadataApi,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from pydantic import ValidationError


class TestTaskInfoApi:
    def test_creates_with_required_fields(self):
        info = TaskInfoApi(
            task_prompt="Test prompt",
            task_input_schema='{"type": "string"}',
            task_output_schema='{"type": "object"}',
        )
        assert info.task_prompt == "Test prompt"
        assert info.task_input_schema == '{"type": "string"}'
        assert info.task_output_schema == '{"type": "object"}'

    def test_missing_required_field_raises_error(self):
        with pytest.raises(ValidationError):
            TaskInfoApi(
                task_prompt="Test prompt",
                task_input_schema='{"type": "string"}',
            )  # type: ignore


class TestTaskMetadataApi:
    def test_creates_with_required_fields(self):
        metadata = TaskMetadataApi(
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
            metadata = TaskMetadataApi(
                model_name="test-model",
                model_provider_name=provider,
            )
            assert metadata.model_provider_name == provider


class TestPromptGenerationResultApi:
    def test_creates_with_required_fields(self):
        metadata = TaskMetadataApi(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
        )
        result = PromptGenerationResultApi(
            task_metadata=metadata,
            prompt="Generated prompt content",
        )
        assert result.task_metadata.model_name == "gpt-4"
        assert result.prompt == "Generated prompt content"


class TestSampleApi:
    def test_creates_with_required_fields(self):
        sample = SampleApi(input="test input", output="test output")
        assert sample.input == "test input"
        assert sample.output == "test output"

    def test_supports_alias_for_input(self):
        # Test that 'input' alias works in dict form
        data = {"input": "aliased input", "output": "test output"}
        sample = SampleApi.model_validate(data)
        assert sample.input == "aliased input"

    def test_model_dump_with_alias(self):
        sample = SampleApi(input="test input", output="test output")
        dumped = sample.model_dump(by_alias=True)
        assert "input" in dumped
        assert dumped["input"] == "test input"


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

    def test_supports_alias_for_input(self):
        data = {
            "input": "aliased input",
            "output": "test output",
            "model_says_meets_spec": True,
            "user_says_meets_spec": True,
            "feedback": "",
        }
        example = ReviewedExample.model_validate(data)
        assert example.input == "aliased input"


class TestSpecApi:
    def test_creates_with_required_fields(self):
        info = SpecApi(
            spec_fields={"field1": "Field 1 description"},
            spec_field_current_values={"field1": "current value"},
        )
        assert info.spec_fields == {"field1": "Field 1 description"}
        assert info.spec_field_current_values == {"field1": "current value"}

    def test_accepts_empty_dicts(self):
        info = SpecApi(
            spec_fields={},
            spec_field_current_values={},
        )
        assert info.spec_fields == {}
        assert info.spec_field_current_values == {}


class TestExampleWithFeedbackApi:
    def test_creates_with_required_fields(self):
        example = ExampleWithFeedbackApi(
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
        example = ExampleWithFeedbackApi(
            user_agrees_with_judge=True,
            input="test input",
            output="test output",
            fails_specification=False,
        )
        assert example.user_feedback is None

    def test_user_feedback_can_be_set(self):
        example = ExampleWithFeedbackApi(
            user_agrees_with_judge=False,
            input="test input",
            output="test output",
            fails_specification=True,
            user_feedback="This is wrong because...",
        )
        assert example.user_feedback == "This is wrong because..."


class TestClarifySpecApiInput:
    def test_creates_with_required_fields(self):
        task_info = TaskInfoApi(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        input_model = ClarifySpecApiInput(
            target_task_info=task_info,
            target_specification="Test spec",
            num_samples_per_topic=5,
            num_topics=3,
            providers=[ModelProviderName.openai],
        )
        assert input_model.target_specification == "Test spec"
        assert input_model.num_samples_per_topic == 5
        assert input_model.num_topics == 3
        assert input_model.num_exemplars == 10  # default

    def test_num_exemplars_default_value(self):
        task_info = TaskInfoApi(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        input_model = ClarifySpecApiInput(
            target_task_info=task_info,
            target_specification="Test spec",
            num_samples_per_topic=5,
            num_topics=3,
            providers=[ModelProviderName.openai],
        )
        assert input_model.num_exemplars == 10


class TestRefineSpecApiInput:
    def test_creates_with_required_fields(self):
        task_info = TaskInfoApi(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        spec_info = SpecApi(
            spec_fields={"field": "description"},
            spec_field_current_values={"field": "value"},
        )
        example = ExampleWithFeedbackApi(
            user_agrees_with_judge=True,
            input="test",
            output="output",
            fails_specification=False,
        )
        input_model = RefineSpecApiInput(
            target_task_info=task_info,
            target_specification=spec_info,
            examples_with_feedback=[example],
        )
        assert len(input_model.examples_with_feedback) == 1


class TestGenerateBatchApiInput:
    def test_creates_with_required_fields(self):
        task_info = TaskInfoApi(
            task_prompt="Test prompt",
            task_input_schema="{}",
            task_output_schema="{}",
        )
        input_model = GenerateBatchApiInput(
            target_task_info=task_info,
            topic_generation_task_info=task_info,
            input_generation_task_info=task_info,
            target_specification="Test spec",
            num_samples_per_topic=5,
            num_topics=10,
        )
        assert input_model.target_specification == "Test spec"
        assert input_model.num_samples_per_topic == 5
        assert input_model.num_topics == 10


class TestSubsampleBatchOutputItemApi:
    def test_creates_with_required_fields(self):
        item = SubsampleBatchOutputItemApi(
            input="test input",
            output="test output",
            fails_specification=True,
        )
        assert item.input == "test input"
        assert item.output == "test output"
        assert item.fails_specification is True


class TestClarifySpecApiOutput:
    def test_creates_with_required_fields(self):
        metadata = TaskMetadataApi(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
        )
        prompt_result = PromptGenerationResultApi(
            task_metadata=metadata,
            prompt="Test prompt",
        )
        example = SubsampleBatchOutputItemApi(
            input="test",
            output="output",
            fails_specification=False,
        )
        output = ClarifySpecApiOutput(
            examples_for_feedback=[example],
            judge_result=prompt_result,
            topic_generation_result=prompt_result,
            input_generation_result=prompt_result,
        )
        assert len(output.examples_for_feedback) == 1
        assert output.judge_result.prompt == "Test prompt"


class TestGenerateBatchApiOutput:
    def test_creates_with_required_fields(self):
        sample = SampleApi(input="test", output="output")
        output = GenerateBatchApiOutput(
            data_by_topic={"topic1": [sample]},
        )
        assert "topic1" in output.data_by_topic
        assert len(output.data_by_topic["topic1"]) == 1

    def test_accepts_empty_data_by_topic(self):
        output = GenerateBatchApiOutput(data_by_topic={})
        assert output.data_by_topic == {}
