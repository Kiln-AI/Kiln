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
        exhibits_issue (bool):
    """

    input_: str
    output: str
    exhibits_issue: bool

    def to_dict(self) -> dict[str, Any]:
        input_ = self.input_

        output = self.output

        exhibits_issue = self.exhibits_issue

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "input": input_,
                "output": output,
                "exhibits_issue": exhibits_issue,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        input_ = d.pop("input")

        output = d.pop("output")

        exhibits_issue = d.pop("exhibits_issue")

        examples_for_feedback_item = cls(
            input_=input_,
            output=output,
            exhibits_issue=exhibits_issue,
        )

        return examples_for_feedback_item
