from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.answer_option_with_selection import AnswerOptionWithSelection


T = TypeVar("T", bound="QuestionWithAnswer")


@_attrs_define
class QuestionWithAnswer:
    """A question with user-provided answer.

    Attributes:
        question_title (str): A short title for this question
        question_body (str): The full question text
        answer_options (list[AnswerOptionWithSelection]): Possible answers the user was asked to select from
        custom_answer (None | str | Unset): User-provided text feedback when predefined answer options don't fit
    """

    question_title: str
    question_body: str
    answer_options: list[AnswerOptionWithSelection]
    custom_answer: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        question_title = self.question_title

        question_body = self.question_body

        answer_options = []
        for answer_options_item_data in self.answer_options:
            answer_options_item = answer_options_item_data.to_dict()
            answer_options.append(answer_options_item)

        custom_answer: None | str | Unset
        if isinstance(self.custom_answer, Unset):
            custom_answer = UNSET
        else:
            custom_answer = self.custom_answer

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "question_title": question_title,
                "question_body": question_body,
                "answer_options": answer_options,
            }
        )
        if custom_answer is not UNSET:
            field_dict["custom_answer"] = custom_answer

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.answer_option_with_selection import AnswerOptionWithSelection

        d = dict(src_dict)
        question_title = d.pop("question_title")

        question_body = d.pop("question_body")

        answer_options = []
        _answer_options = d.pop("answer_options")
        for answer_options_item_data in _answer_options:
            answer_options_item = AnswerOptionWithSelection.from_dict(answer_options_item_data)

            answer_options.append(answer_options_item)

        def _parse_custom_answer(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        custom_answer = _parse_custom_answer(d.pop("custom_answer", UNSET))

        question_with_answer = cls(
            question_title=question_title,
            question_body=question_body,
            answer_options=answer_options,
            custom_answer=custom_answer,
        )

        return question_with_answer
