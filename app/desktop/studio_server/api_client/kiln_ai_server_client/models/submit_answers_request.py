from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.question_with_answer import QuestionWithAnswer
    from ..models.specification_input import SpecificationInput


T = TypeVar("T", bound="SubmitAnswersRequest")


@_attrs_define
class SubmitAnswersRequest:
    """Request to submit answers to a question set.

    Attributes:
        task_prompt (str): The task's prompt
        specification (SpecificationInput): The specification to refine.
        questions_and_answers (list[QuestionWithAnswer]): Questions about the specification with user-provided answers
    """

    task_prompt: str
    specification: SpecificationInput
    questions_and_answers: list[QuestionWithAnswer]

    def to_dict(self) -> dict[str, Any]:
        task_prompt = self.task_prompt

        specification = self.specification.to_dict()

        questions_and_answers = []
        for questions_and_answers_item_data in self.questions_and_answers:
            questions_and_answers_item = questions_and_answers_item_data.to_dict()
            questions_and_answers.append(questions_and_answers_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "task_prompt": task_prompt,
                "specification": specification,
                "questions_and_answers": questions_and_answers,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.question_with_answer import QuestionWithAnswer
        from ..models.specification_input import SpecificationInput

        d = dict(src_dict)
        task_prompt = d.pop("task_prompt")

        specification = SpecificationInput.from_dict(d.pop("specification"))

        questions_and_answers = []
        _questions_and_answers = d.pop("questions_and_answers")
        for questions_and_answers_item_data in _questions_and_answers:
            questions_and_answers_item = QuestionWithAnswer.from_dict(questions_and_answers_item_data)

            questions_and_answers.append(questions_and_answers_item)

        submit_answers_request = cls(
            task_prompt=task_prompt,
            specification=specification,
            questions_and_answers=questions_and_answers,
        )

        return submit_answers_request
