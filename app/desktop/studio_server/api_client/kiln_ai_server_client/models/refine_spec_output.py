from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.refine_spec_output_new_proposed_spec_edits import RefineSpecOutputNewProposedSpecEdits


T = TypeVar("T", bound="RefineSpecOutput")


@_attrs_define
class RefineSpecOutput:
    """
    Attributes:
        new_proposed_spec_edits (RefineSpecOutputNewProposedSpecEdits):
        out_of_scope_feedback (str):
    """

    new_proposed_spec_edits: RefineSpecOutputNewProposedSpecEdits
    out_of_scope_feedback: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        new_proposed_spec_edits = self.new_proposed_spec_edits.to_dict()

        out_of_scope_feedback = self.out_of_scope_feedback

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "new_proposed_spec_edits": new_proposed_spec_edits,
                "out_of_scope_feedback": out_of_scope_feedback,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.refine_spec_output_new_proposed_spec_edits import RefineSpecOutputNewProposedSpecEdits

        d = dict(src_dict)
        new_proposed_spec_edits = RefineSpecOutputNewProposedSpecEdits.from_dict(d.pop("new_proposed_spec_edits"))

        out_of_scope_feedback = d.pop("out_of_scope_feedback")

        refine_spec_output = cls(
            new_proposed_spec_edits=new_proposed_spec_edits,
            out_of_scope_feedback=out_of_scope_feedback,
        )

        refine_spec_output.additional_properties = d
        return refine_spec_output

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
