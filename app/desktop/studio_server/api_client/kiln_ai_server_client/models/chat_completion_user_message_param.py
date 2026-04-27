from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_completion_content_part_image_param import ChatCompletionContentPartImageParam
    from ..models.chat_completion_content_part_input_audio_param import ChatCompletionContentPartInputAudioParam
    from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam
    from ..models.file import File


T = TypeVar("T", bound="ChatCompletionUserMessageParam")


@_attrs_define
class ChatCompletionUserMessageParam:
    """Messages sent by an end user, containing prompts or additional context
    information.

        Attributes:
            content (list[ChatCompletionContentPartImageParam | ChatCompletionContentPartInputAudioParam |
                ChatCompletionContentPartTextParam | File] | str):
            role (Literal['user']):
            name (str | Unset):
    """

    content: (
        list[
            ChatCompletionContentPartImageParam
            | ChatCompletionContentPartInputAudioParam
            | ChatCompletionContentPartTextParam
            | File
        ]
        | str
    )
    role: Literal["user"]
    name: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.chat_completion_content_part_image_param import ChatCompletionContentPartImageParam
        from ..models.chat_completion_content_part_input_audio_param import ChatCompletionContentPartInputAudioParam
        from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam

        content: list[dict[str, Any]] | str
        if isinstance(self.content, list):
            content = []
            for content_type_1_item_data in self.content:
                content_type_1_item: dict[str, Any]
                if isinstance(content_type_1_item_data, ChatCompletionContentPartTextParam):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ChatCompletionContentPartImageParam):
                    content_type_1_item = content_type_1_item_data.to_dict()
                elif isinstance(content_type_1_item_data, ChatCompletionContentPartInputAudioParam):
                    content_type_1_item = content_type_1_item_data.to_dict()
                else:
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
        from ..models.chat_completion_content_part_image_param import ChatCompletionContentPartImageParam
        from ..models.chat_completion_content_part_input_audio_param import ChatCompletionContentPartInputAudioParam
        from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam
        from ..models.file import File

        d = dict(src_dict)

        def _parse_content(
            data: object,
        ) -> (
            list[
                ChatCompletionContentPartImageParam
                | ChatCompletionContentPartInputAudioParam
                | ChatCompletionContentPartTextParam
                | File
            ]
            | str
        ):
            try:
                if not isinstance(data, list):
                    raise TypeError()
                content_type_1 = []
                _content_type_1 = data
                for content_type_1_item_data in _content_type_1:

                    def _parse_content_type_1_item(
                        data: object,
                    ) -> (
                        ChatCompletionContentPartImageParam
                        | ChatCompletionContentPartInputAudioParam
                        | ChatCompletionContentPartTextParam
                        | File
                    ):
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_0 = ChatCompletionContentPartTextParam.from_dict(data)

                            return content_type_1_item_type_0
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_1 = ChatCompletionContentPartImageParam.from_dict(data)

                            return content_type_1_item_type_1
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_2 = ChatCompletionContentPartInputAudioParam.from_dict(data)

                            return content_type_1_item_type_2
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        if not isinstance(data, dict):
                            raise TypeError()
                        content_type_1_item_type_3 = File.from_dict(data)

                        return content_type_1_item_type_3

                    content_type_1_item = _parse_content_type_1_item(content_type_1_item_data)

                    content_type_1.append(content_type_1_item)

                return content_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[
                    ChatCompletionContentPartImageParam
                    | ChatCompletionContentPartInputAudioParam
                    | ChatCompletionContentPartTextParam
                    | File
                ]
                | str,
                data,
            )

        content = _parse_content(d.pop("content"))

        role = cast(Literal["user"], d.pop("role"))
        if role != "user":
            raise ValueError(f"role must match const 'user', got '{role}'")

        name = d.pop("name", UNSET)

        chat_completion_user_message_param = cls(
            content=content,
            role=role,
            name=name,
        )

        chat_completion_user_message_param.additional_properties = d
        return chat_completion_user_message_param

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
