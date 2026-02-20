from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ExamplesWithFeedbackItem")


@_attrs_define
class ExamplesWithFeedbackItem:
    """An example with user feedback on the judge's assessment.

    Attributes:
        user_agrees_with_judge (bool):
        input_ (str):
        output (str):
        fails_specification (bool):
        user_feedback (None | str | Unset):
    """

    user_agrees_with_judge: bool
    input_: str
    output: str
    fails_specification: bool
    user_feedback: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user_agrees_with_judge = self.user_agrees_with_judge

        input_ = self.input_

        output = self.output

        fails_specification = self.fails_specification

        user_feedback: None | str | Unset
        if isinstance(self.user_feedback, Unset):
            user_feedback = UNSET
        else:
            user_feedback = self.user_feedback

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user_agrees_with_judge": user_agrees_with_judge,
                "input": input_,
                "output": output,
                "fails_specification": fails_specification,
            }
        )
        if user_feedback is not UNSET:
            field_dict["user_feedback"] = user_feedback

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_agrees_with_judge = d.pop("user_agrees_with_judge")

        input_ = d.pop("input")

        output = d.pop("output")

        fails_specification = d.pop("fails_specification")

        def _parse_user_feedback(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_feedback = _parse_user_feedback(d.pop("user_feedback", UNSET))

        examples_with_feedback_item = cls(
            user_agrees_with_judge=user_agrees_with_judge,
            input_=input_,
            output=output,
            fails_specification=fails_specification,
            user_feedback=user_feedback,
        )

        examples_with_feedback_item.additional_properties = d
        return examples_with_feedback_item

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
