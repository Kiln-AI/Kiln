"""Tests for kiln_server/utils/spec_utils.py."""

import pytest
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalDataType,
    EvalTemplateId,
    TaskRunSplit,
)
from kiln_ai.datamodel.spec_properties import SpecType
from kiln_server.utils.spec_utils import (
    SpecEvalTags,
    build_spec_eval,
    generate_spec_eval_tags,
    spec_eval_data_type,
    spec_eval_output_score,
    spec_eval_splits,
    spec_eval_template,
    tag_filter_id,
)


def _task(tmp_path) -> Task:
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(name="Test Task", instruction="Test instruction", parent=project)
    task.save_to_file()
    return task


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
            # The legacy tool_call template is reserved for pre-spec LLM tool
            # evals; new tool evals are scored by the tool_call_check judge.
            (SpecType.appropriate_tool_use, None),
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
        test_tag, train_tag, val_tag, golden_tag = generate_spec_eval_tags("Test Spec")
        assert test_tag == "test_test_spec"
        assert train_tag == "train_test_spec"
        assert val_tag == "val_test_spec"
        assert golden_tag == "golden_test_spec"

    def test_handles_already_lowercase_name(self):
        test_tag, train_tag, val_tag, golden_tag = generate_spec_eval_tags("my spec")
        assert test_tag == "test_my_spec"
        assert train_tag == "train_my_spec"
        assert val_tag == "val_my_spec"
        assert golden_tag == "golden_my_spec"

    def test_handles_uppercase_name(self):
        test_tag, train_tag, val_tag, golden_tag = generate_spec_eval_tags("MY SPEC")
        assert test_tag == "test_my_spec"
        assert train_tag == "train_my_spec"
        assert val_tag == "val_my_spec"
        assert golden_tag == "golden_my_spec"

    def test_handles_single_word_name(self):
        test_tag, train_tag, val_tag, golden_tag = generate_spec_eval_tags("Toxicity")
        assert test_tag == "test_toxicity"
        assert train_tag == "train_toxicity"
        assert val_tag == "val_toxicity"
        assert golden_tag == "golden_toxicity"

    def test_no_tag_uses_the_legacy_eval_prefix(self):
        """The four tags share a suffix, so each needs its own distinct prefix.

        The test set's tag was once "eval_"-prefixed. Renaming it is only safe while no
        two tags collide: these are the filters that separate an eval's four datasets, so
        a duplicate silently merges two of them instead of failing.
        """
        tags = generate_spec_eval_tags("Test")

        assert not any(tag.startswith("eval_") for tag in tags)
        assert len(set(tags)) == len(tags)


class TestSpecEvalSplits:
    def test_tag_filter_id_prefixes_the_tag(self):
        assert tag_filter_id("my_tag") == "tag::my_tag"

    def test_splits_are_task_run_backed_tag_filters(self):
        splits = spec_eval_splits(
            test_tag="test_test", train_tag="train_test", val_tag="val_test"
        )

        assert set(splits) == {"test", "train", "val"}
        assert all(isinstance(split, TaskRunSplit) for split in splits.values())
        assert splits["test"].filter_id == "tag::test_test"
        assert splits["train"].filter_id == "tag::train_test"
        assert splits["val"].filter_id == "tag::val_test"


class TestBuildSpecEval:
    def test_returns_the_tags_the_evals_items_must_carry(self, tmp_path):
        eval, tags = build_spec_eval(
            task=_task(tmp_path),
            name="Test Spec",
            spec_type=SpecType.desired_behaviour,
            evaluate_full_trace=False,
        )

        assert tags == SpecEvalTags(
            test_tag="test_test_spec",
            train_tag="train_test_spec",
            val_tag="val_test_spec",
            golden_tag="golden_test_spec",
        )
        assert eval.name == "Test Spec"
        # Golden is not a split, so the split assertions below never cover it.
        assert eval.eval_configs_filter_id == "tag::golden_test_spec"

    def test_splits_are_built_in_one_step(self, tmp_path):
        """All three splits are set, and stored in the one place splits live.

        Asserted on the dump as well as on the model: the deprecated flat filter fields
        are never written, so an eval built here is unreadable to a Kiln build that
        predates `splits` — which is the accepted cost of a single home, and worth
        pinning where it is created.
        """
        eval, _tags = build_spec_eval(
            task=_task(tmp_path),
            name="Test Spec",
            spec_type=SpecType.desired_behaviour,
            evaluate_full_trace=False,
        )

        assert eval.splits == {
            "test": TaskRunSplit(filter_id="tag::test_test_spec"),
            "train": TaskRunSplit(filter_id="tag::train_test_spec"),
            "val": TaskRunSplit(filter_id="tag::val_test_spec"),
        }
        dumped = eval.model_dump()
        assert dumped["eval_set_filter_id"] is None
        assert dumped["train_set_filter_id"] is None
        assert dumped["splits"] == {
            "test": {"source": "task_run", "filter_id": "tag::test_test_spec"},
            "train": {"source": "task_run", "filter_id": "tag::train_test_spec"},
            "val": {"source": "task_run", "filter_id": "tag::val_test_spec"},
        }
