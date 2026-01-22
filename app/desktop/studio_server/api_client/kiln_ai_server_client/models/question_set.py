from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.question import Question


T = TypeVar("T", bound="QuestionSet")


@_attrs_define
class QuestionSet:
    """
    Attributes:
        questions (list[Question]): A set of questions to ask about the specification
    """

    questions: list[Question]

    def to_dict(self) -> dict[str, Any]:
        questions = []
        for questions_item_data in self.questions:
            questions_item = questions_item_data.to_dict()
            questions.append(questions_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "questions": questions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.question import Question

        d = dict(src_dict)
        questions = []
        _questions = d.pop("questions")
        for questions_item_data in _questions:
            questions_item = Question.from_dict(questions_item_data)

            questions.append(questions_item)

        question_set = cls(
            questions=questions,
        )

        return question_set
