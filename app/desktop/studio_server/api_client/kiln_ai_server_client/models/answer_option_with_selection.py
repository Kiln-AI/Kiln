from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AnswerOptionWithSelection")


@_attrs_define
class AnswerOptionWithSelection:
    """An answer option with user selection state.

    Attributes:
        answer_title (str): A short title describing this answer option
        answer_description (str): A description of this answer
        selected (bool): Whether the user selected this answer option
    """

    answer_title: str
    answer_description: str
    selected: bool

    def to_dict(self) -> dict[str, Any]:
        answer_title = self.answer_title

        answer_description = self.answer_description

        selected = self.selected

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "answer_title": answer_title,
                "answer_description": answer_description,
                "selected": selected,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        answer_title = d.pop("answer_title")

        answer_description = d.pop("answer_description")

        selected = d.pop("selected")

        answer_option_with_selection = cls(
            answer_title=answer_title,
            answer_description=answer_description,
            selected=selected,
        )

        return answer_option_with_selection
