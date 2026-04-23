from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam


T = TypeVar("T", bound="ChatCompletionToolMessageParamWrapper")


@_attrs_define
class ChatCompletionToolMessageParamWrapper:
    """
    Attributes:
        content (list[ChatCompletionContentPartTextParam] | str):
        role (Literal['tool']):
        tool_call_id (str):
        kiln_task_tool_data (None | str | Unset):
        is_error (bool | None | Unset):
        error_message (None | str | Unset):
    """

    content: list[ChatCompletionContentPartTextParam] | str
    role: Literal["tool"]
    tool_call_id: str
    kiln_task_tool_data: None | str | Unset = UNSET
    is_error: bool | None | Unset = UNSET
    error_message: None | str | Unset = UNSET
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

        tool_call_id = self.tool_call_id

        kiln_task_tool_data: None | str | Unset
        if isinstance(self.kiln_task_tool_data, Unset):
            kiln_task_tool_data = UNSET
        else:
            kiln_task_tool_data = self.kiln_task_tool_data

        is_error: bool | None | Unset
        if isinstance(self.is_error, Unset):
            is_error = UNSET
        else:
            is_error = self.is_error

        error_message: None | str | Unset
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "content": content,
                "role": role,
                "tool_call_id": tool_call_id,
            }
        )
        if kiln_task_tool_data is not UNSET:
            field_dict["kiln_task_tool_data"] = kiln_task_tool_data
        if is_error is not UNSET:
            field_dict["is_error"] = is_error
        if error_message is not UNSET:
            field_dict["error_message"] = error_message

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

        role = cast(Literal["tool"], d.pop("role"))
        if role != "tool":
            raise ValueError(f"role must match const 'tool', got '{role}'")

        tool_call_id = d.pop("tool_call_id")

        def _parse_kiln_task_tool_data(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        kiln_task_tool_data = _parse_kiln_task_tool_data(d.pop("kiln_task_tool_data", UNSET))

        def _parse_is_error(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        is_error = _parse_is_error(d.pop("is_error", UNSET))

        def _parse_error_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        chat_completion_tool_message_param_wrapper = cls(
            content=content,
            role=role,
            tool_call_id=tool_call_id,
            kiln_task_tool_data=kiln_task_tool_data,
            is_error=is_error,
            error_message=error_message,
        )

        chat_completion_tool_message_param_wrapper.additional_properties = d
        return chat_completion_tool_message_param_wrapper

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
