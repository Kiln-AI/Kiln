from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.new_proposed_spec_edits import NewProposedSpecEdits


T = TypeVar("T", bound="RefineSpecOutputNewProposedSpecEdits")


@_attrs_define
class RefineSpecOutputNewProposedSpecEdits:
    """ """

    additional_properties: dict[str, NewProposedSpecEdits] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.new_proposed_spec_edits import NewProposedSpecEdits

        d = dict(src_dict)
        refine_spec_output_new_proposed_spec_edits = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = NewProposedSpecEdits.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        refine_spec_output_new_proposed_spec_edits.additional_properties = additional_properties
        return refine_spec_output_new_proposed_spec_edits

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> NewProposedSpecEdits:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: NewProposedSpecEdits) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
