from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ExamplesForFeedbackItem")


@_attrs_define
class ExamplesForFeedbackItem:
    """A sample presented for user feedback, with model's judgment.

    Attributes:
        input_ (str):
        output (str):
        fails_specification (bool):
    """

    input_: str
    output: str
    fails_specification: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        input_ = self.input_

        output = self.output

        fails_specification = self.fails_specification

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "input": input_,
                "output": output,
                "fails_specification": fails_specification,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        input_ = d.pop("input")

        output = d.pop("output")

        fails_specification = d.pop("fails_specification")

        examples_for_feedback_item = cls(
            input_=input_,
            output=output,
            fails_specification=fails_specification,
        )

        examples_for_feedback_item.additional_properties = d
        return examples_for_feedback_item

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
