from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam


T = TypeVar("T", bound="ChatCompletionSystemMessageParam")


@_attrs_define
class ChatCompletionSystemMessageParam:
    """Developer-provided instructions that the model should follow, regardless of
    messages sent by the user. With o1 models and newer, use `developer` messages
    for this purpose instead.

        Attributes:
            content (list[ChatCompletionContentPartTextParam] | str):
            role (Literal['system']):
            name (str | Unset):
    """

    content: list[ChatCompletionContentPartTextParam] | str
    role: Literal["system"]
    name: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        content: list[dict[str, Any]] | str
        if isinstance(self.content, list):
            content = []
            for content_type_1_item_data in self.content:
                content_type_1_item = content_type_1_item_data.to_dict()
                content.append(content_type_1_item)

        else:
            content = self.content

        role = self.role

        name = self.name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "content": content,
                "role": role,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam

        d = dict(src_dict)

        def _parse_content(data: object) -> list[ChatCompletionContentPartTextParam] | str:
            try:
                if not isinstance(data, list):
                    raise TypeError()
                content_type_1 = []
                _content_type_1 = data
                for content_type_1_item_data in _content_type_1:
                    content_type_1_item = ChatCompletionContentPartTextParam.from_dict(content_type_1_item_data)

                    content_type_1.append(content_type_1_item)

                return content_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ChatCompletionContentPartTextParam] | str, data)

        content = _parse_content(d.pop("content"))

        role = cast(Literal["system"], d.pop("role"))
        if role != "system":
            raise ValueError(f"role must match const 'system', got '{role}'")

        name = d.pop("name", UNSET)

        chat_completion_system_message_param = cls(
            content=content,
            role=role,
            name=name,
        )

        chat_completion_system_message_param.additional_properties = d
        return chat_completion_system_message_param

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
