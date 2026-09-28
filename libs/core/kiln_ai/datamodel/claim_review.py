from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import KilnParentedModel


class GradedClaim(BaseModel):
    """One claim with a human grade on it.

    A claim is one decision the judge made, written so the reviewer can vote
    on it from the card alone. Grades have one direction on every claim:
    agree means the judge got that decision right, disagree means it got it
    wrong. The claim text carries its own evidence and citation markers.
    """

    text: str = Field(description="The claim as shown to the reviewer.")
    human_grade: Literal["agree", "disagree"] = Field(
        description="The human's grade on this claim."
    )
    human_feedback: str | None = Field(
        default=None,
        description="Optional plaintext reason for the grade.",
    )


def _flip_grade(grade: Any) -> Any:
    if grade == "agree":
        return "disagree"
    if grade == "disagree":
        return "agree"
    return grade


def _upgrade_legacy_claim(claim: Any, judge_score: Any) -> Any:
    """One claim from the earlier claim/evidence shape, in the current shape.

    The earlier shape split a claim into `claim` and `evidence`, and graded it
    against `expected_result`, the verdict an agree supported: agreeing with a
    claim that pointed away from the judge's verdict meant the judge was wrong.
    The current grade means "the judge got this right", so that grade flips.
    """
    if not isinstance(claim, dict) or "text" in claim or "claim" not in claim:
        return claim
    parts = [str(part) for part in (claim.get("claim"), claim.get("evidence")) if part]
    grade = claim.get("human_grade")
    expected = claim.get("expected_result")
    if expected is not None and expected != judge_score:
        grade = _flip_grade(grade)
    return {
        "text": " — ".join(parts),
        "human_grade": grade,
        "human_feedback": claim.get("human_feedback"),
    }


class ClaimReview(KilnParentedModel):
    """A human's grades on the claim summary of one task run.

    Persisted alongside the run's rating so consumers (e.g. judge-prompt
    refinement) can use the full review, which claims were agreed or
    disagreed with and why, not just the final pass/fail. Every claim the
    reviewer saw is recorded with its grade, and the overview is kept so a
    stored review reads on its own.
    """

    judge_score: Literal["pass", "fail"] = Field(
        description="The judge's binary verdict on this run."
    )
    judge_reasoning: str = Field(description="The judge's explanation for its verdict.")
    overview: str = Field(
        description="The neutral summary of the run the reviewer read before "
        "grading the claims."
    )
    claims: list[GradedClaim] = Field(
        description="Every graded claim, in the order the reviewer saw them.",
    )
    human_verdict: Literal["pass", "fail"] = Field(
        description="The reviewer's overall call on this run. Derived from "
        "their grade on the verdict claim when the summary carried one, "
        "otherwise asked directly."
    )

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_claim_evidence_shape(cls, data: Any) -> Any:
        """Read a review saved in the earlier claim/evidence shape.

        Earlier builds saved `claims` as claim/evidence/expected_result entries
        and the overall verdict as a separate `final_judgement` entry, with no
        overview. Those reviews exist in real projects, and a review that fails
        to load fails every read of its run's reviews. They are upgraded in
        memory: each claim becomes one text, the final judgement becomes the
        closing verdict claim, the reviewer's overall call is derived from its
        grade, and the overview is left empty because none was written. The
        file changes only if the review is saved again.
        """
        if not isinstance(data, dict) or "final_judgement" not in data:
            return data
        data = dict(data)
        judge_score = data.get("judge_score")
        final_judgement = data.pop("final_judgement")
        claims = [
            _upgrade_legacy_claim(claim, judge_score)
            for claim in data.get("claims") or []
        ]
        if isinstance(final_judgement, dict):
            claims.append(_upgrade_legacy_claim(final_judgement, judge_score))
            if "human_verdict" not in data and judge_score in ("pass", "fail"):
                # The final judgement always pointed at the judge's verdict, so an
                # agree on it keeps that verdict and a disagree reverses it.
                agreed = final_judgement.get("human_grade") == "agree"
                other = "fail" if judge_score == "pass" else "pass"
                data["human_verdict"] = judge_score if agreed else other
        data["claims"] = claims
        data.setdefault("overview", "")
        return data
