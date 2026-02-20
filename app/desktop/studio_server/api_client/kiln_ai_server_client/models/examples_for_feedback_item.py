from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ExamplesForFeedbackItem")


@_attrs_define
class ExamplesForFeedbackItem:
    """
    Attributes:
        input_ (str):
        output (str):
        fails_specification (bool):
    """

    input_: str
    output: str
    fails_specification: bool

    def to_dict(self) -> dict[str, Any]:
        input_ = self.input_

        output = self.output

        fails_specification = self.fails_specification

        field_dict: dict[str, Any] = {}

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

        return examples_for_feedback_item
