from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AnswerOption")


@_attrs_define
class AnswerOption:
    """
    Attributes:
        answer_title (str): A short title describing this answer option
        answer_description (str): A description of this answer
    """

    answer_title: str
    answer_description: str

    def to_dict(self) -> dict[str, Any]:
        answer_title = self.answer_title

        answer_description = self.answer_description

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "answer_title": answer_title,
                "answer_description": answer_description,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        answer_title = d.pop("answer_title")

        answer_description = d.pop("answer_description")

        answer_option = cls(
            answer_title=answer_title,
            answer_description=answer_description,
        )

        return answer_option
