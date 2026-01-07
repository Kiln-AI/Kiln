from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.spec_info_spec_field_current_values import SpecInfoSpecFieldCurrentValues
    from ..models.spec_info_spec_fields import SpecInfoSpecFields


T = TypeVar("T", bound="SpecInfo")


@_attrs_define
class SpecInfo:
    """
    Attributes:
        spec_fields (SpecInfoSpecFields):
        spec_field_current_values (SpecInfoSpecFieldCurrentValues):
    """

    spec_fields: SpecInfoSpecFields
    spec_field_current_values: SpecInfoSpecFieldCurrentValues
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        spec_fields = self.spec_fields.to_dict()

        spec_field_current_values = self.spec_field_current_values.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "spec_fields": spec_fields,
                "spec_field_current_values": spec_field_current_values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.spec_info_spec_field_current_values import SpecInfoSpecFieldCurrentValues
        from ..models.spec_info_spec_fields import SpecInfoSpecFields

        d = dict(src_dict)
        spec_fields = SpecInfoSpecFields.from_dict(d.pop("spec_fields"))

        spec_field_current_values = SpecInfoSpecFieldCurrentValues.from_dict(d.pop("spec_field_current_values"))

        spec_info = cls(
            spec_fields=spec_fields,
            spec_field_current_values=spec_field_current_values,
        )

        spec_info.additional_properties = d
        return spec_info

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
