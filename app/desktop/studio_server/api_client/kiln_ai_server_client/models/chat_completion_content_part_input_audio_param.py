from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.input_audio import InputAudio


T = TypeVar("T", bound="ChatCompletionContentPartInputAudioParam")


@_attrs_define
class ChatCompletionContentPartInputAudioParam:
    """Learn about [audio inputs](https://platform.openai.com/docs/guides/audio).

    Attributes:
        input_audio (InputAudio):
        type_ (Literal['input_audio']):
    """

    input_audio: InputAudio
    type_: Literal["input_audio"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        input_audio = self.input_audio.to_dict()

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "input_audio": input_audio,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.input_audio import InputAudio

        d = dict(src_dict)
        input_audio = InputAudio.from_dict(d.pop("input_audio"))

        type_ = cast(Literal["input_audio"], d.pop("type"))
        if type_ != "input_audio":
            raise ValueError(f"type must match const 'input_audio', got '{type_}'")

        chat_completion_content_part_input_audio_param = cls(
            input_audio=input_audio,
            type_=type_,
        )

        chat_completion_content_part_input_audio_param.additional_properties = d
        return chat_completion_content_part_input_audio_param

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
