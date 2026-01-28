from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.specification_input_spec_field_current_values import SpecificationInputSpecFieldCurrentValues
    from ..models.specification_input_spec_fields import SpecificationInputSpecFields


T = TypeVar("T", bound="SpecificationInput")


@_attrs_define
class SpecificationInput:
    """The specification to refine.

    Attributes:
        spec_fields (SpecificationInputSpecFields): Dictionary mapping field names to their descriptions/purposes
        spec_field_current_values (SpecificationInputSpecFieldCurrentValues): Dictionary mapping field names to their
            current values
    """

    spec_fields: SpecificationInputSpecFields
    spec_field_current_values: SpecificationInputSpecFieldCurrentValues

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
        from ..models.specification_input_spec_field_current_values import SpecificationInputSpecFieldCurrentValues
        from ..models.specification_input_spec_fields import SpecificationInputSpecFields

        d = dict(src_dict)
        spec_fields = SpecificationInputSpecFields.from_dict(d.pop("spec_fields"))

        spec_field_current_values = SpecificationInputSpecFieldCurrentValues.from_dict(
            d.pop("spec_field_current_values")
        )

        specification_input = cls(
            spec_fields=spec_fields,
            spec_field_current_values=spec_field_current_values,
        )

        return specification_input
