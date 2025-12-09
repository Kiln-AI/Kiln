from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ExampleWithFeedback")


@_attrs_define
class ExampleWithFeedback:
    """
    Attributes:
        user_rating_exhibits_issue_correct (bool):
        input_ (str):
        output (str):
        exhibits_issue (bool):
        user_feedback (None | str | Unset):
    """

    user_rating_exhibits_issue_correct: bool
    input_: str
    output: str
    exhibits_issue: bool
    user_feedback: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user_rating_exhibits_issue_correct = self.user_rating_exhibits_issue_correct

        input_ = self.input_

        output = self.output

        exhibits_issue = self.exhibits_issue

        user_feedback: None | str | Unset
        if isinstance(self.user_feedback, Unset):
            user_feedback = UNSET
        else:
            user_feedback = self.user_feedback

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user_rating_exhibits_issue_correct": user_rating_exhibits_issue_correct,
                "input": input_,
                "output": output,
                "exhibits_issue": exhibits_issue,
            }
        )
        if user_feedback is not UNSET:
            field_dict["user_feedback"] = user_feedback

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_rating_exhibits_issue_correct = d.pop("user_rating_exhibits_issue_correct")

        input_ = d.pop("input")

        output = d.pop("output")

        exhibits_issue = d.pop("exhibits_issue")

        def _parse_user_feedback(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_feedback = _parse_user_feedback(d.pop("user_feedback", UNSET))

        example_with_feedback = cls(
            user_rating_exhibits_issue_correct=user_rating_exhibits_issue_correct,
            input_=input_,
            output=output,
            exhibits_issue=exhibits_issue,
            user_feedback=user_feedback,
        )

        example_with_feedback.additional_properties = d
        return example_with_feedback

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
