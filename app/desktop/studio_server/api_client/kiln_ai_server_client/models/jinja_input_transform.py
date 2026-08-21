from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="JinjaInputTransform")


@_attrs_define
class JinjaInputTransform:
    """Render the task input via a Jinja2 template, producing the first user
    message sent to the model. See specs/projects/templates/functional_spec.md
    for the full contract.

        Attributes:
            template (str): Jinja2 template source. Validated at save time.
            type_ (Literal['jinja'] | Unset):  Default: 'jinja'.
    """

    template: str
    type_: Literal["jinja"] | Unset = "jinja"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        template = self.template

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "template": template,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        template = d.pop("template")

        type_ = cast(Literal["jinja"] | Unset, d.pop("type", UNSET))
        if type_ != "jinja" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'jinja', got '{type_}'")

        jinja_input_transform = cls(
            template=template,
            type_=type_,
        )

        jinja_input_transform.additional_properties = d
        return jinja_input_transform

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
