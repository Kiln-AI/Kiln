from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ChatCompletionContentPartRefusalParam")


@_attrs_define
class ChatCompletionContentPartRefusalParam:
    """
    Attributes:
        refusal (str):
        type_ (Literal['refusal']):
    """

    refusal: str
    type_: Literal["refusal"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        refusal = self.refusal

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "refusal": refusal,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        refusal = d.pop("refusal")

        type_ = cast(Literal["refusal"], d.pop("type"))
        if type_ != "refusal":
            raise ValueError(f"type must match const 'refusal', got '{type_}'")

        chat_completion_content_part_refusal_param = cls(
            refusal=refusal,
            type_=type_,
        )

        chat_completion_content_part_refusal_param.additional_properties = d
        return chat_completion_content_part_refusal_param

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
