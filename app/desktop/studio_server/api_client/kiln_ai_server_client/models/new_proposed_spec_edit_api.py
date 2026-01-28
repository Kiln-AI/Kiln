from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NewProposedSpecEditApi")


@_attrs_define
class NewProposedSpecEditApi:
    """A proposed edit to a spec field.

    Attributes:
        spec_field_name (str):
        proposed_edit (str):
        reason_for_edit (str):
    """

    spec_field_name: str
    proposed_edit: str
    reason_for_edit: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        spec_field_name = self.spec_field_name

        proposed_edit = self.proposed_edit

        reason_for_edit = self.reason_for_edit

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "spec_field_name": spec_field_name,
                "proposed_edit": proposed_edit,
                "reason_for_edit": reason_for_edit,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        spec_field_name = d.pop("spec_field_name")

        proposed_edit = d.pop("proposed_edit")

        reason_for_edit = d.pop("reason_for_edit")

        new_proposed_spec_edit_api = cls(
            spec_field_name=spec_field_name,
            proposed_edit=proposed_edit,
            reason_for_edit=reason_for_edit,
        )

        new_proposed_spec_edit_api.additional_properties = d
        return new_proposed_spec_edit_api

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
