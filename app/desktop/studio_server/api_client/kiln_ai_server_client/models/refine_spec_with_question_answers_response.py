from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.proposed_spec_edit import ProposedSpecEdit


T = TypeVar("T", bound="RefineSpecWithQuestionAnswersResponse")


@_attrs_define
class RefineSpecWithQuestionAnswersResponse:
    """Response containing proposed spec edits based on question answers.

    Attributes:
        new_proposed_spec_edits (list[ProposedSpecEdit]): A list of proposed edits to spec fields
    """

    new_proposed_spec_edits: list[ProposedSpecEdit]

    def to_dict(self) -> dict[str, Any]:
        new_proposed_spec_edits = []
        for new_proposed_spec_edits_item_data in self.new_proposed_spec_edits:
            new_proposed_spec_edits_item = new_proposed_spec_edits_item_data.to_dict()
            new_proposed_spec_edits.append(new_proposed_spec_edits_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "new_proposed_spec_edits": new_proposed_spec_edits,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.proposed_spec_edit import ProposedSpecEdit

        d = dict(src_dict)
        new_proposed_spec_edits = []
        _new_proposed_spec_edits = d.pop("new_proposed_spec_edits")
        for new_proposed_spec_edits_item_data in _new_proposed_spec_edits:
            new_proposed_spec_edits_item = ProposedSpecEdit.from_dict(new_proposed_spec_edits_item_data)

            new_proposed_spec_edits.append(new_proposed_spec_edits_item)

        refine_spec_with_question_answers_response = cls(
            new_proposed_spec_edits=new_proposed_spec_edits,
        )

        return refine_spec_with_question_answers_response
