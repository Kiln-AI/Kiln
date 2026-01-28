"""Tests for kiln_server/utils/spec_utils.py."""

import pytest
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import EvalDataType, EvalTemplateId
from kiln_ai.datamodel.spec_properties import SpecType
from kiln_server.utils.spec_utils import (
    generate_spec_eval_filter_ids,
    generate_spec_eval_tags,
    spec_eval_data_type,
    spec_eval_output_score,
    spec_eval_template,
)


class TestSpecEvalOutputScore:
    def test_creates_eval_output_score_with_correct_name(self):
        score = spec_eval_output_score("Test Spec")
        assert score.name == "Test Spec"

    def test_creates_eval_output_score_with_pass_fail_type(self):
        score = spec_eval_output_score("Test Spec")
        assert score.type == TaskOutputRatingType.pass_fail

    def test_creates_eval_output_score_with_correct_instruction(self):
        score = spec_eval_output_score("Test Spec")
        assert "Test Spec" in score.instruction
        assert "meets the spec" in score.instruction


class TestSpecEvalDataType:
    def test_reference_answer_accuracy_returns_reference_answer(self):
        result = spec_eval_data_type(SpecType.reference_answer_accuracy)
        assert result == EvalDataType.reference_answer

    def test_reference_answer_accuracy_ignores_evaluate_full_trace(self):
        result = spec_eval_data_type(
            SpecType.reference_answer_accuracy, evaluate_full_trace=True
        )
        assert result == EvalDataType.reference_answer

    def test_other_types_default_to_final_answer(self):
        for spec_type in [
            SpecType.desired_behaviour,
            SpecType.issue,
            SpecType.tone,
            SpecType.toxicity,
        ]:
            result = spec_eval_data_type(spec_type)
            assert result == EvalDataType.final_answer

    def test_evaluate_full_trace_returns_full_trace(self):
        result = spec_eval_data_type(
            SpecType.desired_behaviour, evaluate_full_trace=True
        )
        assert result == EvalDataType.full_trace

    def test_evaluate_full_trace_false_returns_final_answer(self):
        result = spec_eval_data_type(
            SpecType.desired_behaviour, evaluate_full_trace=False
        )
        assert result == EvalDataType.final_answer


class TestSpecEvalTemplate:
    @pytest.mark.parametrize(
        "spec_type,expected_template",
        [
            (SpecType.appropriate_tool_use, EvalTemplateId.tool_call),
            (SpecType.reference_answer_accuracy, EvalTemplateId.rag),
            (SpecType.factual_correctness, EvalTemplateId.factual_correctness),
            (SpecType.toxicity, EvalTemplateId.toxicity),
            (SpecType.bias, EvalTemplateId.bias),
            (SpecType.maliciousness, EvalTemplateId.maliciousness),
            (SpecType.jailbreak, EvalTemplateId.jailbreak),
            (SpecType.issue, EvalTemplateId.issue),
            (SpecType.desired_behaviour, EvalTemplateId.desired_behaviour),
        ],
    )
    def test_returns_correct_template_for_spec_type(self, spec_type, expected_template):
        result = spec_eval_template(spec_type)
        assert result == expected_template

    @pytest.mark.parametrize(
        "spec_type",
        [
            SpecType.tone,
            SpecType.formatting,
            SpecType.localization,
            SpecType.hallucinations,
            SpecType.completeness,
            SpecType.nsfw,
            SpecType.taboo,
            SpecType.prompt_leakage,
        ],
    )
    def test_returns_none_for_spec_types_without_template(self, spec_type):
        result = spec_eval_template(spec_type)
        assert result is None


class TestGenerateSpecEvalTags:
    def test_generates_correct_tags_for_simple_name(self):
        eval_tag, train_tag, golden_tag = generate_spec_eval_tags("Test Spec")
        assert eval_tag == "eval_test_spec"
        assert train_tag == "train_test_spec"
        assert golden_tag == "eval_golden_test_spec"

    def test_handles_already_lowercase_name(self):
        eval_tag, train_tag, golden_tag = generate_spec_eval_tags("my spec")
        assert eval_tag == "eval_my_spec"
        assert train_tag == "train_my_spec"
        assert golden_tag == "eval_golden_my_spec"

    def test_handles_uppercase_name(self):
        eval_tag, train_tag, golden_tag = generate_spec_eval_tags("MY SPEC")
        assert eval_tag == "eval_my_spec"
        assert train_tag == "train_my_spec"
        assert golden_tag == "eval_golden_my_spec"

    def test_handles_single_word_name(self):
        eval_tag, train_tag, golden_tag = generate_spec_eval_tags("Toxicity")
        assert eval_tag == "eval_toxicity"
        assert train_tag == "train_toxicity"
        assert golden_tag == "eval_golden_toxicity"

    def test_train_tag_uses_train_prefix(self):
        """Train tag should use 'train_' prefix, not 'eval_train_'."""
        _, train_tag, _ = generate_spec_eval_tags("Test")
        assert train_tag.startswith("train_")
        assert not train_tag.startswith("eval_train_")


class TestGenerateSpecEvalFilterIds:
    def test_generates_correct_filter_ids(self):
        eval_filter, train_filter, golden_filter = generate_spec_eval_filter_ids(
            "eval_test", "train_test", "golden_test"
        )
        assert eval_filter == "tag::eval_test"
        assert train_filter == "tag::train_test"
        assert golden_filter == "tag::golden_test"

    def test_generates_filter_ids_with_tag_prefix(self):
        eval_filter, train_filter, golden_filter = generate_spec_eval_filter_ids(
            "my_tag", "other_tag", "third_tag"
        )
        assert eval_filter.startswith("tag::")
        assert train_filter.startswith("tag::")
        assert golden_filter.startswith("tag::")
