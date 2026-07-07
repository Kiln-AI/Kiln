from typing import Literal

from pydantic import BaseModel, Field

from kiln_ai.datamodel.basemodel import KilnParentedModel


class GradedClaim(BaseModel):
    """One claim/evidence pair with a human grade on it.

    `expected_result` is the verdict an AGREE on the claim supports, so a
    grade is meaningful relative to a judge's verdict: agreeing with a claim
    that points opposite the judge is evidence the judge was wrong.
    """

    claim: str = Field(description="The claim that was graded.")
    evidence: str = Field(description="The one-sentence evidence backing the claim.")
    expected_result: Literal["pass", "fail"] = Field(
        description="The verdict an AGREE on this claim supports."
    )
    human_grade: Literal["agree", "disagree"] = Field(
        description="The human's grade on this claim."
    )
    human_feedback: str | None = Field(
        default=None,
        description="Optional plaintext reason for the grade.",
    )


class ClaimReview(KilnParentedModel):
    """A human's grades on the claim/evidence summary of one task run.

    Persisted alongside the run's rating so consumers (e.g. judge-prompt
    refinement) can use the full review — which claims were agreed or
    disagreed with, and why — not just the final pass/fail. Only claims that
    were actually graded are recorded; the final judgement grade is always
    present.
    """

    judge_score: str = Field(
        description="The judge's verdict on this run, e.g. PASS/FAIL."
    )
    judge_reasoning: str = Field(description="The judge's explanation for its verdict.")
    claims: list[GradedClaim] = Field(
        default=[],
        description="Graded claim/evidence pairs, ordered most- to "
        "least-important. May be empty when only the final judgement was "
        "graded.",
    )
    final_judgement: GradedClaim = Field(
        description="The graded overall-verdict entry; its expected_result "
        "equals the judge's verdict."
    )
