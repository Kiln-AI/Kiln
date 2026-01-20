from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.examples_for_feedback_item import ExamplesForFeedbackItem
    from ..models.judge_info import JudgeInfo


T = TypeVar("T", bound="ClarifySpecOutput")


@_attrs_define
class ClarifySpecOutput:
    """
    Attributes:
        examples_for_feedback (list[ExamplesForFeedbackItem]):
        judge_info (JudgeInfo):
    """

    examples_for_feedback: list[ExamplesForFeedbackItem]
    judge_info: JudgeInfo
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        examples_for_feedback = []
        for examples_for_feedback_item_data in self.examples_for_feedback:
            examples_for_feedback_item = examples_for_feedback_item_data.to_dict()
            examples_for_feedback.append(examples_for_feedback_item)

        judge_info = self.judge_info.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "examples_for_feedback": examples_for_feedback,
                "judge_info": judge_info,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.examples_for_feedback_item import ExamplesForFeedbackItem
        from ..models.judge_info import JudgeInfo

        d = dict(src_dict)
        examples_for_feedback = []
        _examples_for_feedback = d.pop("examples_for_feedback")
        for examples_for_feedback_item_data in _examples_for_feedback:
            examples_for_feedback_item = ExamplesForFeedbackItem.from_dict(examples_for_feedback_item_data)

            examples_for_feedback.append(examples_for_feedback_item)

        judge_info = JudgeInfo.from_dict(d.pop("judge_info"))

        clarify_spec_output = cls(
            examples_for_feedback=examples_for_feedback,
            judge_info=judge_info,
        )

        clarify_spec_output.additional_properties = d
        return clarify_spec_output

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
