from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mcp_tool_reference import MCPToolReference


T = TypeVar("T", bound="McpRunConfigProperties")


@_attrs_define
class McpRunConfigProperties:
    """A configuration for running a task via an MCP tool.

    Attributes:
        tool_reference (MCPToolReference):
        type_ (Literal['mcp'] | Unset):  Default: 'mcp'.
    """

    tool_reference: MCPToolReference
    type_: Literal["mcp"] | Unset = "mcp"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool_reference = self.tool_reference.to_dict()

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_reference": tool_reference,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mcp_tool_reference import MCPToolReference

        d = dict(src_dict)
        tool_reference = MCPToolReference.from_dict(d.pop("tool_reference"))

        type_ = cast(Literal["mcp"] | Unset, d.pop("type", UNSET))
        if type_ != "mcp" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'mcp', got '{type_}'")

        mcp_run_config_properties = cls(
            tool_reference=tool_reference,
            type_=type_,
        )

        mcp_run_config_properties.additional_properties = d
        return mcp_run_config_properties

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
