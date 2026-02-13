from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.entitlement import Entitlement


T = TypeVar("T", bound="EntitlementsList")


@_attrs_define
class EntitlementsList:
    """
    Attributes:
        entitlements (list[Entitlement]):
    """

    entitlements: list[Entitlement]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        entitlements = []
        for entitlements_item_data in self.entitlements:
            entitlements_item = entitlements_item_data.to_dict()
            entitlements.append(entitlements_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "entitlements": entitlements,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.entitlement import Entitlement

        d = dict(src_dict)
        entitlements = []
        _entitlements = d.pop("entitlements")
        for entitlements_item_data in _entitlements:
            entitlements_item = Entitlement.from_dict(entitlements_item_data)

            entitlements.append(entitlements_item)

        entitlements_list = cls(
            entitlements=entitlements,
        )

        entitlements_list.additional_properties = d
        return entitlements_list

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
