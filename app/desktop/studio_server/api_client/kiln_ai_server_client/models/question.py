from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.answer_option import AnswerOption


T = TypeVar("T", bound="Question")


@_attrs_define
class Question:
    """
    Attributes:
        question_title (str): A short title for this question
        question_body (str): The full question text
        answer_options (list[AnswerOption]): A list of possible answers to this question for the user to select from
    """

    question_title: str
    question_body: str
    answer_options: list[AnswerOption]

    def to_dict(self) -> dict[str, Any]:
        question_title = self.question_title

        question_body = self.question_body

        answer_options = []
        for answer_options_item_data in self.answer_options:
            answer_options_item = answer_options_item_data.to_dict()
            answer_options.append(answer_options_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "question_title": question_title,
                "question_body": question_body,
                "answer_options": answer_options,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.answer_option import AnswerOption

        d = dict(src_dict)
        question_title = d.pop("question_title")

        question_body = d.pop("question_body")

        answer_options = []
        _answer_options = d.pop("answer_options")
        for answer_options_item_data in _answer_options:
            answer_options_item = AnswerOption.from_dict(answer_options_item_data)

            answer_options.append(answer_options_item)

        question = cls(
            question_title=question_title,
            question_body=question_body,
            answer_options=answer_options,
        )

        return question
