from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ExamplesWithFeedbackItem")


@_attrs_define
class ExamplesWithFeedbackItem:
    """
    Attributes:
        user_rating_exhibits_issue_correct (bool): Whether the user's pass/fail rating was correct
        input_ (str):
        output (str):
        exhibits_issue (bool): Whether the output actually exhibits the issue
        user_feedback (None | str | Unset): Optional text feedback from the user
    """

    user_rating_exhibits_issue_correct: bool
    input_: str
    output: str
    exhibits_issue: bool
    user_feedback: None | str | Unset = UNSET

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

        examples_with_feedback_item = cls(
            user_rating_exhibits_issue_correct=user_rating_exhibits_issue_correct,
            input_=input_,
            output=output,
            exhibits_issue=exhibits_issue,
            user_feedback=user_feedback,
        )

        return examples_with_feedback_item
