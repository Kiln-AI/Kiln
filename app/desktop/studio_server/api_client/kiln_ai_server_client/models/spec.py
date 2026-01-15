from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.spec_spec_field_current_values import SpecSpecFieldCurrentValues
    from ..models.spec_spec_fields import SpecSpecFields


T = TypeVar("T", bound="Spec")


@_attrs_define
class Spec:
    """
    Attributes:
        spec_fields (SpecSpecFields): Dictionary mapping field names to their descriptions/purposes
        spec_field_current_values (SpecSpecFieldCurrentValues): Dictionary mapping field names to their current values
    """

    spec_fields: SpecSpecFields
    spec_field_current_values: SpecSpecFieldCurrentValues

    def to_dict(self) -> dict[str, Any]:
        spec_fields = self.spec_fields.to_dict()

        spec_field_current_values = self.spec_field_current_values.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "spec_fields": spec_fields,
                "spec_field_current_values": spec_field_current_values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.spec_spec_field_current_values import SpecSpecFieldCurrentValues
        from ..models.spec_spec_fields import SpecSpecFields

        d = dict(src_dict)
        spec_fields = SpecSpecFields.from_dict(d.pop("spec_fields"))

        spec_field_current_values = SpecSpecFieldCurrentValues.from_dict(d.pop("spec_field_current_values"))

        spec = cls(
            spec_fields=spec_fields,
            spec_field_current_values=spec_field_current_values,
        )

        return spec
