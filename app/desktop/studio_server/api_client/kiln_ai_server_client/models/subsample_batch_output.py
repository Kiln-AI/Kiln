from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.subsample_batch_output_item import SubsampleBatchOutputItem


T = TypeVar("T", bound="SubsampleBatchOutput")


@_attrs_define
class SubsampleBatchOutput:
    """
    Attributes:
        examples_for_feedback (list[SubsampleBatchOutputItem]):
    """

    examples_for_feedback: list[SubsampleBatchOutputItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        examples_for_feedback = []
        for examples_for_feedback_item_data in self.examples_for_feedback:
            examples_for_feedback_item = examples_for_feedback_item_data.to_dict()
            examples_for_feedback.append(examples_for_feedback_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "examples_for_feedback": examples_for_feedback,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subsample_batch_output_item import SubsampleBatchOutputItem

        d = dict(src_dict)
        examples_for_feedback = []
        _examples_for_feedback = d.pop("examples_for_feedback")
        for examples_for_feedback_item_data in _examples_for_feedback:
            examples_for_feedback_item = SubsampleBatchOutputItem.from_dict(examples_for_feedback_item_data)

            examples_for_feedback.append(examples_for_feedback_item)

        subsample_batch_output = cls(
            examples_for_feedback=examples_for_feedback,
        )

        subsample_batch_output.additional_properties = d
        return subsample_batch_output

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
