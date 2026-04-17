from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ChatCompletionFunctionMessageParam")


@_attrs_define
class ChatCompletionFunctionMessageParam:
    """
    Attributes:
        content (None | str):
        name (str):
        role (Literal['function']):
    """

    content: None | str
    name: str
    role: Literal["function"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        content: None | str
        content = self.content

        name = self.name

        role = self.role

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "content": content,
                "name": name,
                "role": role,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_content(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        content = _parse_content(d.pop("content"))

        name = d.pop("name")

        role = cast(Literal["function"], d.pop("role"))
        if role != "function":
            raise ValueError(f"role must match const 'function', got '{role}'")

        chat_completion_function_message_param = cls(
            content=content,
            name=name,
            role=role,
        )

        chat_completion_function_message_param.additional_properties = d
        return chat_completion_function_message_param

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
