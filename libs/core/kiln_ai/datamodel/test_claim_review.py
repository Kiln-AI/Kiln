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
        "text": "The agent stated a 30-day return window as fact [1].",
        "human_grade": "agree",
        "human_feedback": None,
    }
    values.update(overrides)
    return GradedClaim(**values)


def _review(**overrides) -> ClaimReview:
    values = {
        "judge_score": "fail",
        "judge_reasoning": "Fabricated a policy.",
        "overview": "The user asked about returns and the agent quoted a window.",
        "claims": [_graded_claim()],
        "human_verdict": "fail",
    }
    values.update(overrides)
    return ClaimReview(**values)


class TestClaimReviewModel:
    def test_create_claim_review(self):
        review = _review(
            claims=[
                _graded_claim(),
                _graded_claim(
                    text="It fails because the window was never verified [1].",
                    human_grade="disagree",
                    human_feedback="Policy is real.",
                ),
            ],
            human_verdict="pass",
        )
        assert review.judge_score == "fail"
        assert review.overview.startswith("The user asked")
        assert review.claims[1].human_feedback == "Policy is real."
        assert review.human_verdict == "pass"
        assert review.id is not None

    def test_rejects_invalid_grades_and_verdicts(self):
        with pytest.raises(ValidationError):
            _graded_claim(human_grade="maybe")
        with pytest.raises(ValidationError):
            _review(human_verdict="unsure")

    def test_requires_the_overall_call_and_the_overview(self):
        # The overall call is what the golden rating is built from, and the
        # overview is what makes a stored review readable on its own; neither
        # may be silently defaulted.
        with pytest.raises(ValidationError):
            ClaimReview(
                judge_score="fail",
                judge_reasoning="Fabricated a policy.",
                overview="Summary.",
                claims=[_graded_claim()],
            )
        with pytest.raises(ValidationError):
            ClaimReview(
                judge_score="fail",
                judge_reasoning="Fabricated a policy.",
                claims=[_graded_claim()],
                human_verdict="fail",
            )


class TestClaimReviewPersistence:
    def test_save_and_load_roundtrip(self, task_and_run):
        _, run = task_and_run
        review = _review(
            claims=[_graded_claim(human_grade="disagree", human_feedback="why")],
            parent=run,
        )
        review.save_to_file()

        assert review.path is not None and review.path.exists()
        loaded = ClaimReview.load_from_file(review.path)
        assert loaded.id == review.id
        assert loaded.overview == review.overview
        assert loaded.claims[0].text == review.claims[0].text
        assert loaded.claims[0].human_grade == "disagree"
        assert loaded.human_verdict == "fail"

        with open(review.path) as f:
            data = json.load(f)
        assert data["judge_score"] == "fail"
        assert data["human_verdict"] == "fail"
        assert data["claims"][0]["human_feedback"] == "why"

    def test_accessor_on_task_run(self, task_and_run):
        _, run = task_and_run
        assert run.claim_reviews() == []
        review = _review(judge_score="pass", human_verdict="pass", parent=run)
        review.save_to_file()
        reviews = run.claim_reviews(readonly=True)
        assert len(reviews) == 1
        assert reviews[0].judge_score == "pass"
        assert ClaimReview.parent_type().__name__ == "TaskRun"
        assert ClaimReview.relationship_name() == "claim_reviews"


def _legacy_claim(**overrides) -> dict:
    values = {
        "claim": "The agent stated a return window as fact.",
        "evidence": "The reply gives a window of 30 days [1].",
        "expected_result": "fail",
        "human_grade": "agree",
        "human_feedback": None,
    }
    values.update(overrides)
    return values


def _legacy_review(**overrides) -> dict:
    """A review in the claim/evidence shape earlier builds saved."""
    values = {
        "judge_score": "fail",
        "judge_reasoning": "Fabricated a policy.",
        "claims": [_legacy_claim()],
        "final_judgement": _legacy_claim(
            claim="Eval fails",
            evidence="The window was never verified [1].",
            expected_result="fail",
        ),
    }
    values.update(overrides)
    return values


class TestLegacyClaimEvidenceShape:
    def test_upgrades_claims_and_verdict(self):
        review = ClaimReview.model_validate(_legacy_review())
        assert review.overview == ""
        assert [claim.text for claim in review.claims] == [
            "The agent stated a return window as fact. — The reply gives a window of 30 days [1].",
            "Eval fails — The window was never verified [1].",
        ]
        assert [claim.human_grade for claim in review.claims] == ["agree", "agree"]
        assert review.human_verdict == "fail"

    def test_grade_flips_on_a_claim_pointing_away_from_the_judge(self):
        # Agreeing with a claim that supports the other verdict meant the judge
        # was wrong, which the current grade records as a disagree.
        review = ClaimReview.model_validate(
            _legacy_review(
                claims=[
                    _legacy_claim(expected_result="pass", human_grade="agree"),
                    _legacy_claim(
                        expected_result="pass",
                        human_grade="disagree",
                        human_feedback="why",
                    ),
                ]
            )
        )
        assert [claim.human_grade for claim in review.claims[:2]] == [
            "disagree",
            "agree",
        ]
        assert review.claims[1].human_feedback == "why"

    def test_disagreeing_with_the_final_judgement_reverses_the_verdict(self):
        review = ClaimReview.model_validate(
            _legacy_review(
                final_judgement=_legacy_claim(
                    expected_result="fail", human_grade="disagree"
                )
            )
        )
        assert review.human_verdict == "pass"
        assert review.claims[-1].human_grade == "disagree"

    def test_legacy_file_loads_through_the_task_run(self, task_and_run):
        _, run = task_and_run
        assert run.path is not None
        review_dir = run.path.parent / "claim_reviews" / "123456789012"
        review_dir.mkdir(parents=True)
        legacy = {"v": 1, "id": "123456789012", "model_type": "claim_review"}
        legacy.update(_legacy_review(judge_score="pass", claims=[]))
        legacy["final_judgement"] = _legacy_claim(
            claim="Eval passes", expected_result="pass"
        )
        with open(review_dir / "claim_review.kiln", "w") as f:
            json.dump(legacy, f)

        reviews = run.claim_reviews(readonly=True)
        assert len(reviews) == 1
        assert reviews[0].human_verdict == "pass"
        assert reviews[0].claims[0].text.startswith("Eval passes")
