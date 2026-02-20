from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.examples_with_feedback_item import ExamplesWithFeedbackItem
    from ..models.specification_input import SpecificationInput
    from ..models.task_info import TaskInfo


T = TypeVar("T", bound="RefineSpecInput")


@_attrs_define
class RefineSpecInput:
    """
    Attributes:
        target_task_info (TaskInfo): Shared information about a task
        target_specification (SpecificationInput): The specification to refine.
        examples_with_feedback (list[ExamplesWithFeedbackItem]):
    """

    target_task_info: TaskInfo
    target_specification: SpecificationInput
    examples_with_feedback: list[ExamplesWithFeedbackItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        target_task_info = self.target_task_info.to_dict()

        target_specification = self.target_specification.to_dict()

        examples_with_feedback = []
        for examples_with_feedback_item_data in self.examples_with_feedback:
            examples_with_feedback_item = examples_with_feedback_item_data.to_dict()
            examples_with_feedback.append(examples_with_feedback_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "target_task_info": target_task_info,
                "target_specification": target_specification,
                "examples_with_feedback": examples_with_feedback,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.examples_with_feedback_item import ExamplesWithFeedbackItem
        from ..models.specification_input import SpecificationInput
        from ..models.task_info import TaskInfo

        d = dict(src_dict)
        target_task_info = TaskInfo.from_dict(d.pop("target_task_info"))

        target_specification = SpecificationInput.from_dict(d.pop("target_specification"))

        examples_with_feedback = []
        _examples_with_feedback = d.pop("examples_with_feedback")
        for examples_with_feedback_item_data in _examples_with_feedback:
            examples_with_feedback_item = ExamplesWithFeedbackItem.from_dict(examples_with_feedback_item_data)

            examples_with_feedback.append(examples_with_feedback_item)

        refine_spec_input = cls(
            target_task_info=target_task_info,
            target_specification=target_specification,
            examples_with_feedback=examples_with_feedback,
        )

        refine_spec_input.additional_properties = d
        return refine_spec_input

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
