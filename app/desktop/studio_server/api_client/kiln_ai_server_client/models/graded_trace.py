from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.judge_score import JudgeScore

if TYPE_CHECKING:
    from ..models.graded_claim import GradedClaim
    from ..models.graded_final_judgement import GradedFinalJudgement


T = TypeVar("T", bound="GradedTrace")


@_attrs_define
class GradedTrace:
    """
    Attributes:
        trace_label (str): Short identifier for the trace — often an opaque run id rather than a human-readable name.
            Cite it as given in change rationales.
        judge_score (JudgeScore):
        judge_reasoning (str): The judge's explanation for its verdict.
        claims (list[GradedClaim]): The claim/evidence pairs the reviewer actually graded, in the claim builder's most-
            to-least-important order. A SUBSET of what the builder produced — absent claims were not reviewed, which is no
            signal (never agreement). May be empty.
        final_judgement (GradedFinalJudgement):
    """

    trace_label: str
    judge_score: JudgeScore
    judge_reasoning: str
    claims: list[GradedClaim]
    final_judgement: GradedFinalJudgement
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        trace_label = self.trace_label

        judge_score = self.judge_score.value

        judge_reasoning = self.judge_reasoning

        claims = []
        for claims_item_data in self.claims:
            claims_item = claims_item_data.to_dict()
            claims.append(claims_item)

        final_judgement = self.final_judgement.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "trace_label": trace_label,
                "judge_score": judge_score,
                "judge_reasoning": judge_reasoning,
                "claims": claims,
                "final_judgement": final_judgement,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.graded_claim import GradedClaim
        from ..models.graded_final_judgement import GradedFinalJudgement

        d = dict(src_dict)
        trace_label = d.pop("trace_label")

        judge_score = JudgeScore(d.pop("judge_score"))

        judge_reasoning = d.pop("judge_reasoning")

        claims = []
        _claims = d.pop("claims")
        for claims_item_data in _claims:
            claims_item = GradedClaim.from_dict(claims_item_data)

            claims.append(claims_item)

        final_judgement = GradedFinalJudgement.from_dict(d.pop("final_judgement"))

        graded_trace = cls(
            trace_label=trace_label,
            judge_score=judge_score,
            judge_reasoning=judge_reasoning,
            claims=claims,
            final_judgement=final_judgement,
        )

        graded_trace.additional_properties = d
        return graded_trace

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
