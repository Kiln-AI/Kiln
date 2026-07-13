from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.expected_result import ExpectedResult
from ..models.human_grade import HumanGrade

T = TypeVar("T", bound="GradedFinalJudgement")


@_attrs_define
class GradedFinalJudgement:
    """
    Attributes:
        claim (str): The overall verdict as a claim, e.g. 'Eval passes'.
        evidence (str): The one-sentence evidence shown to the reviewer.
        expected_result (ExpectedResult):
        human_grade (HumanGrade):
        human_feedback (None | str): The reviewer's optional plaintext 'why'. Null if left blank.
    """

    claim: str
    evidence: str
    expected_result: ExpectedResult
    human_grade: HumanGrade
    human_feedback: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claim = self.claim

        evidence = self.evidence

        expected_result = self.expected_result.value

        human_grade = self.human_grade.value

        human_feedback: None | str
        human_feedback = self.human_feedback

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "claim": claim,
                "evidence": evidence,
                "expected_result": expected_result,
                "human_grade": human_grade,
                "human_feedback": human_feedback,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        claim = d.pop("claim")

        evidence = d.pop("evidence")

        expected_result = ExpectedResult(d.pop("expected_result"))

        human_grade = HumanGrade(d.pop("human_grade"))

        def _parse_human_feedback(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        human_feedback = _parse_human_feedback(d.pop("human_feedback"))

        graded_final_judgement = cls(
            claim=claim,
            evidence=evidence,
            expected_result=expected_result,
            human_grade=human_grade,
            human_feedback=human_feedback,
        )

        graded_final_judgement.additional_properties = d
        return graded_final_judgement

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
