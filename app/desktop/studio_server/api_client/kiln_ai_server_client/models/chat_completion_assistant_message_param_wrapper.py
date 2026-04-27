from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.audio import Audio
    from ..models.chat_completion_content_part_refusal_param import ChatCompletionContentPartRefusalParam
    from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam
    from ..models.chat_completion_message_function_tool_call_param import ChatCompletionMessageFunctionToolCallParam
    from ..models.function_call import FunctionCall


T = TypeVar("T", bound="ChatCompletionAssistantMessageParamWrapper")


@_attrs_define
class ChatCompletionAssistantMessageParamWrapper:
    """Almost exact copy of ChatCompletionAssistantMessageParam, but two changes.

    First change: List[T] instead of Iterable[T] for tool_calls. Addresses pydantic issue.
    https://github.com/pydantic/pydantic/issues/9541

    Second change: Add reasoning_content to the message. A LiteLLM property for reasoning data.

        Attributes:
            role (Literal['assistant']):
            audio (Audio | None | Unset):
            content (list[ChatCompletionContentPartRefusalParam | ChatCompletionContentPartTextParam] | None | str | Unset):
            reasoning_content (None | str | Unset):
            function_call (FunctionCall | None | Unset):
            name (str | Unset):
            refusal (None | str | Unset):
            tool_calls (list[ChatCompletionMessageFunctionToolCallParam] | Unset):
    """

    role: Literal["assistant"]
    audio: Audio | None | Unset = UNSET
    content: list[ChatCompletionContentPartRefusalParam | ChatCompletionContentPartTextParam] | None | str | Unset = (
        UNSET
    )
    reasoning_content: None | str | Unset = UNSET
    function_call: FunctionCall | None | Unset = UNSET
    name: str | Unset = UNSET
    refusal: None | str | Unset = UNSET
    tool_calls: list[ChatCompletionMessageFunctionToolCallParam] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.audio import Audio
        from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam
        from ..models.function_call import FunctionCall

        role = self.role

        audio: dict[str, Any] | None | Unset
        if isinstance(self.audio, Unset):
            audio = UNSET
        elif isinstance(self.audio, Audio):
            audio = self.audio.to_dict()
        else:
            audio = self.audio

        content: list[dict[str, Any]] | None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        elif isinstance(self.content, list):
            content = []
            for content_type_1_item_data in self.content:
                content_type_1_item: dict[str, Any]
                if isinstance(content_type_1_item_data, ChatCompletionContentPartTextParam):
                    content_type_1_item = content_type_1_item_data.to_dict()
                else:
                    content_type_1_item = content_type_1_item_data.to_dict()

                content.append(content_type_1_item)

        else:
            content = self.content

        reasoning_content: None | str | Unset
        if isinstance(self.reasoning_content, Unset):
            reasoning_content = UNSET
        else:
            reasoning_content = self.reasoning_content

        function_call: dict[str, Any] | None | Unset
        if isinstance(self.function_call, Unset):
            function_call = UNSET
        elif isinstance(self.function_call, FunctionCall):
            function_call = self.function_call.to_dict()
        else:
            function_call = self.function_call

        name = self.name

        refusal: None | str | Unset
        if isinstance(self.refusal, Unset):
            refusal = UNSET
        else:
            refusal = self.refusal

        tool_calls: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.tool_calls, Unset):
            tool_calls = []
            for tool_calls_item_data in self.tool_calls:
                tool_calls_item = tool_calls_item_data.to_dict()
                tool_calls.append(tool_calls_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "role": role,
            }
        )
        if audio is not UNSET:
            field_dict["audio"] = audio
        if content is not UNSET:
            field_dict["content"] = content
        if reasoning_content is not UNSET:
            field_dict["reasoning_content"] = reasoning_content
        if function_call is not UNSET:
            field_dict["function_call"] = function_call
        if name is not UNSET:
            field_dict["name"] = name
        if refusal is not UNSET:
            field_dict["refusal"] = refusal
        if tool_calls is not UNSET:
            field_dict["tool_calls"] = tool_calls

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.audio import Audio
        from ..models.chat_completion_content_part_refusal_param import ChatCompletionContentPartRefusalParam
        from ..models.chat_completion_content_part_text_param import ChatCompletionContentPartTextParam
        from ..models.chat_completion_message_function_tool_call_param import ChatCompletionMessageFunctionToolCallParam
        from ..models.function_call import FunctionCall

        d = dict(src_dict)
        role = cast(Literal["assistant"], d.pop("role"))
        if role != "assistant":
            raise ValueError(f"role must match const 'assistant', got '{role}'")

        def _parse_audio(data: object) -> Audio | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                audio_type_0 = Audio.from_dict(data)

                return audio_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Audio | None | Unset, data)

        audio = _parse_audio(d.pop("audio", UNSET))

        def _parse_content(
            data: object,
        ) -> list[ChatCompletionContentPartRefusalParam | ChatCompletionContentPartTextParam] | None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                content_type_1 = []
                _content_type_1 = data
                for content_type_1_item_data in _content_type_1:

                    def _parse_content_type_1_item(
                        data: object,
                    ) -> ChatCompletionContentPartRefusalParam | ChatCompletionContentPartTextParam:
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            content_type_1_item_type_0 = ChatCompletionContentPartTextParam.from_dict(data)

                            return content_type_1_item_type_0
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        if not isinstance(data, dict):
                            raise TypeError()
                        content_type_1_item_type_1 = ChatCompletionContentPartRefusalParam.from_dict(data)

                        return content_type_1_item_type_1

                    content_type_1_item = _parse_content_type_1_item(content_type_1_item_data)

                    content_type_1.append(content_type_1_item)

                return content_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[ChatCompletionContentPartRefusalParam | ChatCompletionContentPartTextParam] | None | str | Unset,
                data,
            )

        content = _parse_content(d.pop("content", UNSET))

        def _parse_reasoning_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reasoning_content = _parse_reasoning_content(d.pop("reasoning_content", UNSET))

        def _parse_function_call(data: object) -> FunctionCall | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                function_call_type_0 = FunctionCall.from_dict(data)

                return function_call_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(FunctionCall | None | Unset, data)

        function_call = _parse_function_call(d.pop("function_call", UNSET))

        name = d.pop("name", UNSET)

        def _parse_refusal(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        refusal = _parse_refusal(d.pop("refusal", UNSET))

        _tool_calls = d.pop("tool_calls", UNSET)
        tool_calls: list[ChatCompletionMessageFunctionToolCallParam] | Unset = UNSET
        if _tool_calls is not UNSET:
            tool_calls = []
            for tool_calls_item_data in _tool_calls:
                tool_calls_item = ChatCompletionMessageFunctionToolCallParam.from_dict(tool_calls_item_data)

                tool_calls.append(tool_calls_item)

        chat_completion_assistant_message_param_wrapper = cls(
            role=role,
            audio=audio,
            content=content,
            reasoning_content=reasoning_content,
            function_call=function_call,
            name=name,
            refusal=refusal,
            tool_calls=tool_calls,
        )

        chat_completion_assistant_message_param_wrapper.additional_properties = d
        return chat_completion_assistant_message_param_wrapper

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
