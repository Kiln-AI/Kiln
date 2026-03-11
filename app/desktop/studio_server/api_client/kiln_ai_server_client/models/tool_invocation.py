from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.tool_invocation_state import ToolInvocationState

T = TypeVar("T", bound="ToolInvocation")


@_attrs_define
class ToolInvocation:
    """
    Attributes:
        state (ToolInvocationState):
        tool_call_id (str):
        tool_name (str):
        args (Any):
        result (Any):
    """

    state: ToolInvocationState
    tool_call_id: str
    tool_name: str
    args: Any
    result: Any
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        state = self.state.value

        tool_call_id = self.tool_call_id

        tool_name = self.tool_name

        args = self.args

        result = self.result

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "state": state,
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "args": args,
                "result": result,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        state = ToolInvocationState(d.pop("state"))

        tool_call_id = d.pop("toolCallId")

        tool_name = d.pop("toolName")

        args = d.pop("args")

        result = d.pop("result")

        tool_invocation = cls(
            state=state,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            args=args,
            result=result,
        )

        tool_invocation.additional_properties = d
        return tool_invocation

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
