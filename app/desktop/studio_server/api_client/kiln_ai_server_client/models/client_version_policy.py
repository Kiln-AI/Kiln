from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClientVersionPolicy")


@_attrs_define
class ClientVersionPolicy:
    """
    Attributes:
        required (bool):
        upgrade_nudge_version (None | str | Unset):
    """

    required: bool
    upgrade_nudge_version: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        required = self.required

        upgrade_nudge_version: None | str | Unset
        if isinstance(self.upgrade_nudge_version, Unset):
            upgrade_nudge_version = UNSET
        else:
            upgrade_nudge_version = self.upgrade_nudge_version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "required": required,
            }
        )
        if upgrade_nudge_version is not UNSET:
            field_dict["upgrade_nudge_version"] = upgrade_nudge_version

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        required = d.pop("required")

        def _parse_upgrade_nudge_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        upgrade_nudge_version = _parse_upgrade_nudge_version(d.pop("upgrade_nudge_version", UNSET))

        client_version_policy = cls(
            required=required,
            upgrade_nudge_version=upgrade_nudge_version,
        )

        client_version_policy.additional_properties = d
        return client_version_policy

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
