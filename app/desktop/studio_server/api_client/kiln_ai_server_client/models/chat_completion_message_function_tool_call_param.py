from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.function import Function


T = TypeVar("T", bound="ChatCompletionMessageFunctionToolCallParam")


@_attrs_define
class ChatCompletionMessageFunctionToolCallParam:
    """A call to a function tool created by the model.

    Attributes:
        id (str):
        function (Function): The function that the model called.
        type_ (Literal['function']):
    """

    id: str
    function: Function
    type_: Literal["function"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        function = self.function.to_dict()

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "function": function,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.function import Function

        d = dict(src_dict)
        id = d.pop("id")

        function = Function.from_dict(d.pop("function"))

        type_ = cast(Literal["function"], d.pop("type"))
        if type_ != "function":
            raise ValueError(f"type must match const 'function', got '{type_}'")

        chat_completion_message_function_tool_call_param = cls(
            id=id,
            function=function,
            type_=type_,
        )

        chat_completion_message_function_tool_call_param.additional_properties = d
        return chat_completion_message_function_tool_call_param

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
