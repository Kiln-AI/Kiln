import json

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel import (
    ClaimReview,
    DataSource,
    DataSourceType,
    GradedClaim,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)


@pytest.fixture
def task_and_run(tmp_path):
    project = Project(
        name="Test Project", path=tmp_path / "test_project" / "project.kiln"
    )
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="Do something",
        parent=project,
    )
    task.save_to_file()
    run = TaskRun(
        parent=task,
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "tester"}
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test_model",
                    "model_provider": "openai",
                    "adapter_name": "test_adapter",
                    "prompt_id": "simple_prompt_builder",
                },
            ),
        ),
    )
    run.save_to_file()
    return task, run


def _graded_claim(**overrides) -> GradedClaim:
    values = {
        "claim": "The agent stated a return window as fact.",
        "evidence": "The reply gives a window of 30 days [1].",
        "expected_result": "fail",
        "human_grade": "agree",
        "human_feedback": None,
    }
    values.update(overrides)
    return GradedClaim(**values)


class TestClaimReviewModel:
    def test_create_claim_review(self):
        review = ClaimReview(
            judge_score="fail",
            judge_reasoning="Fabricated a policy.",
            claims=[_graded_claim()],
            final_judgement=_graded_claim(
                human_grade="disagree", human_feedback="Policy is real."
            ),
        )
        assert review.judge_score == "fail"
        assert review.claims[0].expected_result == "fail"
        assert review.final_judgement.human_feedback == "Policy is real."
        assert review.id is not None

    def test_claims_may_be_empty(self):
        review = ClaimReview(
            judge_score="pass",
            judge_reasoning="Fine.",
            final_judgement=_graded_claim(expected_result="pass"),
        )
        assert review.claims == []

    def test_rejects_invalid_grades(self):
        with pytest.raises(ValidationError):
            _graded_claim(human_grade="maybe")
        with pytest.raises(ValidationError):
            _graded_claim(expected_result="unsure")


class TestClaimReviewPersistence:
    def test_save_and_load_roundtrip(self, task_and_run):
        _, run = task_and_run
        review = ClaimReview(
            judge_score="fail",
            judge_reasoning="Fabricated a policy.",
            claims=[_graded_claim()],
            final_judgement=_graded_claim(human_grade="disagree", human_feedback="why"),
            parent=run,
        )
        review.save_to_file()

        assert review.path is not None and review.path.exists()
        loaded = ClaimReview.load_from_file(review.path)
        assert loaded.id == review.id
        assert loaded.claims[0].claim == review.claims[0].claim
        assert loaded.final_judgement.human_grade == "disagree"

        with open(review.path) as f:
            data = json.load(f)
        assert data["judge_score"] == "fail"
        assert data["final_judgement"]["human_feedback"] == "why"

    def test_accessor_on_task_run(self, task_and_run):
        _, run = task_and_run
        assert run.claim_reviews() == []
        review = ClaimReview(
            judge_score="pass",
            judge_reasoning="Fine.",
            final_judgement=_graded_claim(expected_result="pass"),
            parent=run,
        )
        review.save_to_file()
        reviews = run.claim_reviews(readonly=True)
        assert len(reviews) == 1
        assert reviews[0].judge_score == "pass"
        assert ClaimReview.parent_type().__name__ == "TaskRun"
        assert ClaimReview.relationship_name() == "claim_reviews"
