from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.judge_score import JudgeScore

T = TypeVar("T", bound="BuildClaimEvidenceInput")


@_attrs_define
class BuildClaimEvidenceInput:
    """
    Attributes:
        raw_input (str): The task's raw input, verbatim. Part of the trace and GROUND TRUTH. For conversational tasks,
            the conversation's opening user message. Anchor citations into this with source 'input'.
        raw_output (str): The task's raw output, verbatim. Part of the trace and GROUND TRUTH. For conversational tasks,
            the full multi-speaker transcript (role-labelled turns in <role_message> tags). Anchor citations into this with
            source 'output'.
        eval_rubric (str): The prompt the judge ran with — the rubric judge_score was produced under. Take hints from it
            but QUESTION it; may be under-specified or wrong.
        judge_reasoning (str): The judge's explanation. May be thin or a mechanical placeholder; validate against the
            trace, never treat as truth or required evidence.
        judge_score (JudgeScore):
    """

    raw_input: str
    raw_output: str
    eval_rubric: str
    judge_reasoning: str
    judge_score: JudgeScore
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        raw_input = self.raw_input

        raw_output = self.raw_output

        eval_rubric = self.eval_rubric

        judge_reasoning = self.judge_reasoning

        judge_score = self.judge_score.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "raw_input": raw_input,
                "raw_output": raw_output,
                "eval_rubric": eval_rubric,
                "judge_reasoning": judge_reasoning,
                "judge_score": judge_score,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        raw_input = d.pop("raw_input")

        raw_output = d.pop("raw_output")

        eval_rubric = d.pop("eval_rubric")

        judge_reasoning = d.pop("judge_reasoning")

        judge_score = JudgeScore(d.pop("judge_score"))

        build_claim_evidence_input = cls(
            raw_input=raw_input,
            raw_output=raw_output,
            eval_rubric=eval_rubric,
            judge_reasoning=judge_reasoning,
            judge_score=judge_score,
        )

        build_claim_evidence_input.additional_properties = d
        return build_claim_evidence_input

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
